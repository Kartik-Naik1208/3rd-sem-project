import re
from pathlib import Path

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


# Safety scoring weights per level (0-100 scale, lower = safer)
SAFETY_SCORE_WEIGHTS = {
    'Safe': 0,
    'Caution': 15,
    'Harmful': 35,
    'Avoid': 25,       # legacy label; treated between Caution and Harmful
    'Unknown': 5,
}

# Max deduction is capped at 100 (score floor = 0)
# Score formula: 100 - sum(per-ingredient penalty) capped at [0, 100]
# Penalty per ingredient = SAFETY_SCORE_WEIGHTS[safety_level]
# Verdict thresholds:
#   >= 85  → "Clean & Safe"
#   >= 60  → "Moderate Caution"
#    < 60  → "High Risk"


def clean_text(raw_text):
    """Clean and normalize raw ingredient text before tokenization or matching.

    - Handles None and empty inputs safely, returning an empty string.
    - Strips leading and trailing whitespace.
    - Replaces line breaks, tabs, and special whitespace with single spaces.
    - Normalizes multiple spaces into a single space.
    - Removes common leading ingredient label prefixes (e.g. 'Ingredients:', 'Contains:', 'May contain:').
    - Preserves all ingredient names, commas/semicolons, and E-numbers (e.g. 'E621', 'E 330').
    """
    if raw_text is None:
        return ""
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    # Replace newlines, carriage returns, tabs with space
    cleaned = re.sub(r'[\r\n\t\f]+', ' ', raw_text)

    # Remove common ingredient label prefixes (case-insensitive)
    cleaned = re.sub(
        r'^\s*(ingredients|contains|may contain)\s*[:\-]\s*',
        '',
        cleaned,
        flags=re.IGNORECASE,
    )

    # Normalize multiple spaces into a single space
    cleaned = re.sub(r'\s+', ' ', cleaned)

    return cleaned.strip()


class IngredientAnalyzer:
    """Analyzes raw OCR text or ingredient lists using fuzzy matching and the SQLAlchemy database.

    When used inside an active Flask application context the analyzer queries the
    ingredients table directly for up-to-date data. Outside a Flask context (e.g.,
    standalone scripts or tests) it falls back to data/ingredients.csv.
    """

    clean_text = staticmethod(clean_text)

    COMMON_ALLERGENS = {
        'Gluten': ['wheat', 'barley', 'rye', 'malt', 'flour'],
        'Dairy': ['milk', 'whey', 'casein', 'butter', 'lactose', 'cheese', 'cream'],
        'Soy': ['soy', 'soya', 'soybean', 'lecithin'],
        'Peanuts': ['peanut', 'arachis'],
        'Tree Nuts': ['almond', 'walnut', 'cashew', 'pistachio', 'hazelnut', 'pecan'],
        'Eggs': ['egg', 'albumin', 'globulin'],
        'Fish & Shellfish': ['fish', 'salmon', 'tuna', 'shrimp', 'crab', 'lobster', 'prawn'],
        'Sulfites': ['sulfite', 'sulphite', 'sulfur dioxide', 'e220', 'e221', 'e222', 'e223', 'e224', 'e228'],
    }

    def __init__(self):
        # Catalog is populated lazily on first use to support both app-context and standalone modes.
        self._catalog = None

    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = self._load_catalog()
        return self._catalog

    def _load_catalog(self):
        """Load ingredient catalog. Tries Flask DB first, falls back to CSV."""
        # 1. Try SQLAlchemy within an active Flask application context
        try:
            from flask import current_app
            if current_app:
                from app.models.ingredient import Ingredient
                items = Ingredient.query.all()
                if items:
                    return [self._model_to_dict(i) for i in items]
        except RuntimeError:
            # No active application context – acceptable in tests/scripts
            pass
        except Exception:
            pass

        # 2. Fallback: load from data/ingredients.csv
        return self._load_csv_catalog()

    def refresh_catalog(self):
        """Force-reload the catalog (call after seeding DB)."""
        self._catalog = None

    def _model_to_dict(self, ingredient):
        """Convert an Ingredient ORM model instance to the dict format used internally."""
        # Normalise safety label: the model has both safety_level (CSV) and safety_rating (legacy).
        safety = ingredient.safety_level or ingredient.safety_rating or 'Safe'
        return {
            'name': ingredient.name,
            'aliases': ingredient.aliases or '',
            'e_number': ingredient.e_number,
            'category': ingredient.category or 'General',
            'safety_rating': safety,   # keep key as safety_rating for template compatibility
            'safety_level': safety,
            'allergen_type': ingredient.allergen_type,
            'allergen_tag': ingredient.allergen_tag or '',
            'diet_flags': ingredient.diet_flags or '',
            'description': ingredient.description,
            'health_effects': ingredient.health_effects,
            'banned_status': ingredient.banned_status,
        }

    def _load_csv_catalog(self):
        """Load catalog from data/ingredients.csv (fallback path)."""
        import csv
        csv_path = Path(__file__).resolve().parent.parent.parent / 'data' / 'ingredients.csv'
        if not csv_path.exists():
            return []
        catalog = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    safety = row.get('safety_level', 'Safe')
                    catalog.append({
                        'name': row['name'],
                        'aliases': row.get('aliases', ''),
                        'e_number': row.get('e_number') or None,
                        'category': row.get('category', 'General'),
                        'safety_rating': safety,
                        'safety_level': safety,
                        'allergen_type': None,
                        'allergen_tag': row.get('allergen_tag', ''),
                        'diet_flags': row.get('diet_flags', ''),
                        'description': None,
                        'health_effects': row.get('health_effects'),
                        'banned_status': row.get('banned_status', 'False') == 'True',
                    })
        except Exception:
            pass
        return catalog

    # ------------------------------------------------------------------ #
    # Token parsing                                                        #
    # ------------------------------------------------------------------ #

    def parse_tokens(self, raw_text):
        """Split raw ingredient label text into distinct candidate ingredient names.

        Rules:
        - Clean text using clean_text() to safely handle None/empty, normalize whitespace, and strip prefixes.
        - Split on commas, semicolons, bullets, newlines.
        - For each chunk, extract the ingredient name separately from any trailing E-number
          parenthetical so tokens like 'sodium benzoate (E211)' yield a single clean token
          'sodium benzoate' rather than 'sodium benzoate E211'.
        - Discard pure digit tokens or single-character fragments.
        """
        if raw_text is None:
            return []

        cleaned = clean_text(raw_text)
        if not cleaned:
            return []

        # Split on list separators
        raw_items = re.split(r'[,;•\n\r]+', cleaned)

        tokens = []
        seen_lower = set()

        for item in raw_items:
            item = item.strip()
            if not item:
                continue

            # Remove trailing parentheticals that are ONLY an E-number
            # e.g. "(E211)" or "(e 330)" — keep the base name clean
            item_no_enum = re.sub(
                r'\s*\(\s*[eE]\s*\d{3,4}[a-zA-Z]?\s*\)',
                '',
                item,
            ).strip()

            # Also remove any remaining parentheses and special chars
            trimmed = re.sub(r'[\[\]\{\}\.\*]', '', item_no_enum).strip()
            # Collapse multiple spaces
            trimmed = re.sub(r'\s+', ' ', trimmed)

            if not trimmed or len(trimmed) < 2 or trimmed.isdigit():
                continue

            key = trimmed.lower()
            if key in seen_lower:
                continue          # skip duplicates
            seen_lower.add(key)
            tokens.append(trimmed)

        return tokens

    # ------------------------------------------------------------------ #
    # Matching                                                             #
    # ------------------------------------------------------------------ #

    def _build_index(self):
        """Build name and alias lookup structures from the catalog."""
        names = []           # lowercase canonical names parallel to catalog
        alias_map = {}       # lowercase alias -> catalog index
        e_map = {}           # normalised E-number -> catalog index

        for idx, item in enumerate(self.catalog):
            names.append(item['name'].lower())

            if item.get('e_number'):
                norm_e = item['e_number'].replace(' ', '').upper()
                e_map[norm_e] = idx

            for alias in re.split(r'[,;]+', item.get('aliases') or ''):
                alias = alias.strip().lower()
                if alias:
                    alias_map[alias] = idx

        return names, alias_map, e_map

    def match_ingredient(self, token, score_cutoff=72):
        """Return (catalog_dict, confidence_score) for the best match or (None, 0)."""
        token_lower = token.lower().strip()
        catalog = self.catalog

        if not catalog:
            return None, 0.0

        names, alias_map, e_map = self._build_index()

        # 1. Direct E-number match (highest priority, confidence 100)
        e_hit = re.search(r'\b(e\s*[-]?\d{3,4}[a-zA-Z]?)\b', token_lower)
        if e_hit:
            norm_e = e_hit.group(1).replace(' ', '').replace('-', '').upper()
            if norm_e in e_map:
                return catalog[e_map[norm_e]], 100.0

        # 2. Exact name match (case-insensitive)
        if token_lower in names:
            return catalog[names.index(token_lower)], 100.0

        # 3. Alias match (case-insensitive exact)
        if token_lower in alias_map:
            return catalog[alias_map[token_lower]], 95.0

        # 4. Fuzzy match against canonical names
        if RAPIDFUZZ_AVAILABLE:
            match_result = process.extractOne(
                token_lower,
                names,
                scorer=fuzz.WRatio,
                score_cutoff=score_cutoff,
            )
            if match_result:
                matched_name, score, idx = match_result
                return catalog[idx], round(score, 1)

            # 5. Fuzzy match against aliases
            alias_keys = list(alias_map.keys())
            if alias_keys:
                alias_result = process.extractOne(
                    token_lower,
                    alias_keys,
                    scorer=fuzz.WRatio,
                    score_cutoff=score_cutoff,
                )
                if alias_result:
                    matched_alias, score, _ = alias_result
                    idx = alias_map[matched_alias]
                    return catalog[idx], round(score, 1)
        else:
            # Substring fallback
            for item in catalog:
                if item['name'].lower() in token_lower or token_lower in item['name'].lower():
                    return item, 85.0
            for alias_key, idx in alias_map.items():
                if alias_key in token_lower or token_lower in alias_key:
                    return catalog[idx], 80.0

        return None, 0.0

    # ------------------------------------------------------------------ #
    # Scoring                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def compute_score(detected_ingredients):
        """Compute a 0-100 safety score from a list of detected ingredient dicts.

        Formula:
          score = 100 - Σ penalty(safety_level)  clamped to [0, 100]

        Penalties per distinct ingredient:
          Safe    →  0 points deducted
          Caution → 15 points deducted
          Avoid   → 25 points deducted  (legacy label)
          Harmful → 35 points deducted
          Unknown →  5 points deducted

        Repeated ingredients in the input list are deduplicated to prevent
        unfair penalty inflation.
        The score is a transparency indicator, NOT a medical assessment.
        """
        if not detected_ingredients:
            return 100

        total_penalty = 0
        seen = set()
        for ing in detected_ingredients:
            name = (ing.get('matched_name') or ing.get('name') or ing.get('raw_token') or '').lower().strip()
            if name:
                if name in seen:
                    continue
                seen.add(name)
            safety = ing.get('safety_rating') or ing.get('safety_level') or 'Safe'
            total_penalty += SAFETY_SCORE_WEIGHTS.get(safety, 5)
        return max(0, min(100, 100 - total_penalty))

    @staticmethod
    def score_to_verdict(score):
        """Convert numeric score to a human-readable verdict + badge class."""
        if score >= 85:
            return 'Clean & Safe', 'success'
        elif score >= 60:
            return 'Moderate Caution', 'warning'
        else:
            return 'High Risk', 'danger'

    # ------------------------------------------------------------------ #
    # Main analysis pipeline                                               #
    # ------------------------------------------------------------------ #

    def analyze(self, raw_text, user_allergies=None, user_diet=None):
        """Full analysis pipeline: parse → match → flag allergens → check preferences → score → verdict."""
        tokens = self.parse_tokens(raw_text)
        detected_list = []
        flagged_allergens = set()
        caution_count = 0
        avoid_count = 0
        harmful_count = 0

        # Normalize user preferences
        if user_allergies is None:
            user_allergies = []
        user_allergies_normalized = set(a.strip().lower() for a in user_allergies if a.strip())

        user_diet_normalized = (user_diet or '').strip().lower()
        if user_diet_normalized in ('none', ''):
            user_diet_normalized = None

        personal_conflicts = []  # List of dicts: {'ingredient': name, 'type': 'allergy'|'diet', 'detail': ...}

        for token in tokens:
            matched_item, score = self.match_ingredient(token)

            if matched_item:
                safety = matched_item.get('safety_rating') or matched_item.get('safety_level') or 'Safe'
                allergen_tag = matched_item.get('allergen_tag') or ''
                diet_flags = matched_item.get('diet_flags') or ''

                info = {
                    'raw_token': token,
                    'matched_name': matched_item['name'],
                    'e_number': matched_item.get('e_number'),
                    'category': matched_item.get('category', 'General'),
                    'safety_rating': safety,
                    'safety_level': safety,
                    'allergen_type': matched_item.get('allergen_type'),
                    'allergen_tag': allergen_tag,
                    'diet_flags': diet_flags,
                    'description': matched_item.get('description', ''),
                    'health_effects': matched_item.get('health_effects', ''),
                    'confidence': round(score, 1),
                    'banned_status': matched_item.get('banned_status', False),
                }
                detected_list.append(info)

                # Allergen from DB field
                if info['allergen_type']:
                    flagged_allergens.add(info['allergen_type'])

                # Infer allergen from name/alias for common triggers
                for allergen_label, keywords in self.COMMON_ALLERGENS.items():
                    if any(kw in token.lower() or kw in matched_item['name'].lower()
                           for kw in keywords):
                        flagged_allergens.add(allergen_label)

                # --- Personal Allergy / Diet Conflict Checking ---
                # Check allergen_tag against user_allergies (exact token match in comma-separated list)
                item_tags = [t.strip().lower() for t in allergen_tag.split(',') if t.strip()]
                for tag in item_tags:
                    if tag in user_allergies_normalized:
                        conflict_msg = f"{matched_item['name']}: matches your selected {tag} allergy."
                        if conflict_msg not in [c['message'] for c in personal_conflicts]:
                            personal_conflicts.append({
                                'ingredient': matched_item['name'],
                                'type': 'allergy',
                                'tag': tag,
                                'message': conflict_msg
                            })

                # Check diet_flags against user_diet (exact token match in comma-separated list)
                if user_diet_normalized:
                    item_diets = [d.strip().lower() for d in diet_flags.split(',') if d.strip()]
                    if user_diet_normalized in item_diets:
                        conflict_msg = f"{matched_item['name']}: conflicts with your {user_diet_normalized} diet."
                        if conflict_msg not in [c['message'] for c in personal_conflicts]:
                            personal_conflicts.append({
                                'ingredient': matched_item['name'],
                                'type': 'diet',
                                'diet': user_diet_normalized,
                                'message': conflict_msg
                            })

                if safety == 'Caution':
                    caution_count += 1
                elif safety == 'Avoid':
                    avoid_count += 1
                elif safety == 'Harmful':
                    harmful_count += 1
            else:
                # Unmatched token — infer allergens from keywords
                for allergen_label, keywords in self.COMMON_ALLERGENS.items():
                    if any(kw in token.lower() for kw in keywords):
                        flagged_allergens.add(allergen_label)

                detected_list.append({
                    'raw_token': token,
                    'matched_name': token,
                    'e_number': None,
                    'category': 'Uncategorized',
                    'safety_rating': 'Safe',
                    'safety_level': 'Safe',
                    'allergen_type': None,
                    'allergen_tag': '',
                    'diet_flags': '',
                    'description': 'Ingredient not found in database.',
                    'health_effects': None,
                    'confidence': 0.0,
                    'banned_status': False,
                })

        # Compute score and verdict
        safety_score = self.compute_score(detected_list)
        base_verdict, base_badge = self.score_to_verdict(safety_score)

        # Personal conflict override:
        # If any selected allergy matches or any dietary conflict is detected,
        # override the displayed verdict to "Avoid"
        has_conflict = len(personal_conflicts) > 0
        if has_conflict:
            displayed_verdict = 'Avoid'
            displayed_badge = 'danger'
        else:
            displayed_verdict = base_verdict
            displayed_badge = base_badge

        return {
            'tokens': tokens,
            'detected_ingredients': detected_list,
            'flagged_allergens': sorted(flagged_allergens),
            'summary': displayed_verdict,
            'badge_class': displayed_badge,
            'base_verdict': base_verdict,
            'safety_score': safety_score,
            'has_conflict': has_conflict,
            'personal_conflicts': personal_conflicts,
            'user_allergies': list(user_allergies_normalized),
            'user_diet': user_diet_normalized,
            'stats': {
                'total_detected': len(detected_list),
                'caution_count': caution_count,
                'avoid_count': avoid_count,
                'harmful_count': harmful_count,
                'allergen_count': len(flagged_allergens),
            },
        }

    def search_ingredients(self, query):
        """
        Search ingredients in database with exact, partial, and difflib fuzzy matching.
        Returns a list of matching ingredient dicts ranked by relevance.
        """
        import difflib

        if not query:
            return []

        q_norm = query.strip().lower()
        if not q_norm:
            return []

        q_enum = q_norm.replace(' ', '').replace('-', '')
        if q_enum.isdigit():
            q_enum = 'e' + q_enum

        catalog = self.catalog
        if not catalog:
            return []

        # 1. Exact matches (Name, E-number, Alias)
        exact_matches = []
        seen_names = set()

        for item in catalog:
            name_lower = (item.get('name') or '').strip().lower()
            enum_lower = (item.get('e_number') or '').strip().lower().replace(' ', '')
            aliases_list = [a.strip().lower() for a in (item.get('aliases') or '').split(',') if a.strip()]

            is_exact = False
            priority = 0
            if q_norm == name_lower:
                is_exact = True
                priority = 3
            elif q_enum and enum_lower and q_enum == enum_lower:
                is_exact = True
                priority = 2
            elif q_norm in aliases_list:
                is_exact = True
                priority = 1

            if is_exact and name_lower not in seen_names:
                exact_matches.append((priority, item))
                seen_names.add(name_lower)

        if exact_matches:
            exact_matches.sort(key=lambda x: x[0], reverse=True)
            return [item for _, item in exact_matches]

        # 2. Partial matches (substring in Name, E-number, or Alias)
        partial_matches = []
        for item in catalog:
            name_lower = (item.get('name') or '').strip().lower()
            if name_lower in seen_names:
                continue

            enum_lower = (item.get('e_number') or '').strip().lower().replace(' ', '')
            aliases_list = [a.strip().lower() for a in (item.get('aliases') or '').split(',') if a.strip()]

            match_score = 0
            if q_norm in name_lower:
                match_score = 3 if name_lower.startswith(q_norm) else 2
            elif q_enum and enum_lower and q_enum in enum_lower:
                match_score = 2
            elif any(q_norm in a for a in aliases_list):
                match_score = 1

            if match_score > 0:
                partial_matches.append((match_score, item))
                seen_names.add(name_lower)

        if partial_matches:
            partial_matches.sort(key=lambda x: x[0], reverse=True)
            return [item for _, item in partial_matches]

        # 3. Fuzzy matches using difflib for typos (e.g. 'caseen' -> 'casein' -> Milk powder)
        fuzzy_matches = []
        cutoff = 0.65

        for item in catalog:
            name_lower = (item.get('name') or '').strip().lower()
            if name_lower in seen_names:
                continue

            enum_lower = (item.get('e_number') or '').strip().lower().replace(' ', '')
            aliases_list = [a.strip().lower() for a in (item.get('aliases') or '').split(',') if a.strip()]

            best_ratio = difflib.SequenceMatcher(None, q_norm, name_lower).ratio()

            if enum_lower:
                e_ratio = difflib.SequenceMatcher(None, q_enum, enum_lower).ratio()
                if e_ratio > best_ratio:
                    best_ratio = e_ratio

            for alias in aliases_list:
                a_ratio = difflib.SequenceMatcher(None, q_norm, alias).ratio()
                if a_ratio > best_ratio:
                    best_ratio = a_ratio
                for word in alias.split():
                    w_ratio = difflib.SequenceMatcher(None, q_norm, word).ratio()
                    if w_ratio > best_ratio:
                        best_ratio = w_ratio

            for word in name_lower.split():
                w_ratio = difflib.SequenceMatcher(None, q_norm, word).ratio()
                if w_ratio > best_ratio:
                    best_ratio = w_ratio

            if best_ratio >= cutoff:
                fuzzy_matches.append((best_ratio, item))

        if fuzzy_matches:
            fuzzy_matches.sort(key=lambda x: x[0], reverse=True)
            return [item for _, item in fuzzy_matches]

        return []
