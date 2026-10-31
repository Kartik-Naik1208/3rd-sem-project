import re
from pathlib import Path

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


SOUTHAMPTON_DYES = {
    'tartrazine', 'e102', 'sunset yellow', 'e110', 'allura red', 'e129',
    'carmoisine', 'e122', 'ponceau 4r', 'e124', 'quinoline yellow', 'e104'
}

INTENSE_SWEETENERS = {
    'aspartame', 'e951', 'acesulfame k', 'acesulfame potassium', 'e950',
    'sucralose', 'e955', 'saccharin', 'e954', 'neotame', 'e961', 'advantame', 'e969'
}

CURING_SALTS = {
    'sodium nitrite', 'e250', 'sodium nitrate', 'e251',
    'potassium nitrite', 'e249', 'potassium nitrate', 'e252'
}

CAFFEINE_STIMULANTS = {
    'caffeine', 'guarana', 'taurine', 'coffee extract', 'kola nut'
}

PRESERVATIVES_SENSITIZING = {
    'sodium benzoate', 'e211', 'potassium sorbate', 'e202', 'sulfur dioxide',
    'e220', 'sodium sulfite', 'e221', 'sodium metabisulfite', 'e223', 'potassium metabisulfite', 'e224'
}

COSMETIC_INDICATORS = {
    'sodium laureth sulfate', 'sodium lauryl sulfate', 'dimethicone', 'paraben',
    'methylparaben', 'propylparaben', 'fragrance', 'parfum', 'cyclopentasiloxane'
}

# Safety scoring weights per level (0-100 scale, lower = safer)
SAFETY_SCORE_WEIGHTS = {
    'Safe': 0,
    'Caution': 15,
    'Harmful': 35,
    'Avoid': 25,       # legacy label; treated between Caution and Harmful
    'Unknown': 5,
}

CATEGORY_FUNCTION_MAP = {
    'Acidity Regulator': {
        'what_it_does': 'Controls and balances acidity or tartness, helping food stay fresh and maintain flavor.',
        'simple_explanation': 'A food-grade compound that adjusts pH acidity so the product stays fresh, crisp, and properly preserved.',
        'regular_consumption': 'Standard dietary ingredient; safe for regular consumption in normal culinary amounts.',
    },
    'Anticaking Agent': {
        'what_it_does': 'Prevents dry powders, seasonings, and salts from clumping in humid conditions.',
        'simple_explanation': 'A fine mineral substance added to dry foods so they pour freely and stay powdery.',
        'regular_consumption': 'Consumed in minimal trace quantities; recognized as safe by global food authorities.',
    },
    'Antioxidant': {
        'what_it_does': 'Prevents dietary fats and oils from turning rancid or losing nutritional freshness.',
        'simple_explanation': 'A protective compound (often a vitamin such as vitamin C or E) that shields food from oxygen breakdown.',
        'regular_consumption': 'Standard food protector; widely and safely consumed across daily foods.',
    },
    'Artificial Sweetener': {
        'what_it_does': 'Provides intense sweetness without the caloric carbohydrates of natural sugar.',
        'simple_explanation': 'A concentrated non-sugar chemical substitute engineered to taste sweet with virtually zero calories.',
        'regular_consumption': 'Pediatric and global health bodies (WHO 2023) advise moderation and caution against routine habitual intake.',
    },
    'Sweetener': {
        'what_it_does': 'Imparts sweetness and pleasant flavor to foods and beverages.',
        'simple_explanation': 'A sweetening substance used to enhance flavor and sweetness.',
        'regular_consumption': 'Health authorities advise moderating added sweeteners to reduce metabolic strain and dental cavities.',
    },
    'Bulking Agent': {
        'what_it_does': 'Increases the volume and weight of food without adding substantial calories.',
        'simple_explanation': 'A dietary ingredient that adds substance, texture, and body to food formulations.',
        'regular_consumption': 'Standard food ingredient; generally reasonable for normal dietary intake.',
    },
    'Dairy': {
        'what_it_does': 'Provides rich dairy creaminess, natural calcium, and protein structure.',
        'simple_explanation': 'A wholesome substance originating from milk (such as milk powder, whey, or cheese).',
        'regular_consumption': 'Wholesome dietary component for non-allergic individuals; avoid if you have a milk allergy or severe lactose intolerance.',
    },
    'Emulsifier': {
        'what_it_does': 'Blends water and oil together so ingredients do not separate over time.',
        'simple_explanation': 'A food binder that keeps liquids, dressings, and creams smoothly mixed with an even texture.',
        'regular_consumption': 'Standard food binder; safe in routine diets, though moderation of ultra-processed foods is recommended.',
    },
    'Fat and Oil': {
        'what_it_does': 'Provides moisture, rich flavor, mouthfeel, and cooking stability.',
        'simple_explanation': 'A natural plant or animal lipid that carries flavor and provides dietary fatty acids.',
        'regular_consumption': 'Best enjoyed in moderation; prefer unsaturated vegetable oils over partially hydrogenated or highly saturated fats.',
    },
    'Flavour Enhancer': {
        'what_it_does': 'Intensifies and enriches savory (umami) flavors in foods and seasonings.',
        'simple_explanation': 'A compound that activates savory taste buds to make soups, snacks, and seasonings taste richer.',
        'regular_consumption': 'Approved as safe by FDA and EFSA; sensitive individuals occasionally report mild temporary symptoms from very high amounts.',
    },
    'Flour Treatment Agent': {
        'what_it_does': 'Improves baking quality, dough elasticity, and bread rising.',
        'simple_explanation': 'A substance added to flour to strengthen the dough structure during baking.',
        'regular_consumption': 'Consumed in trace residual amounts in finished baked goods; standard culinary additive.',
    },
    'Food Colour': {
        'what_it_does': 'Adds vibrant visual color to replace color lost during processing or make foods look appealing.',
        'simple_explanation': 'A pigment (natural or synthetic) added strictly for visual appearance.',
        'regular_consumption': 'Purely aesthetic with no nutritional value; pediatric guidelines encourage limiting synthetic dyes.',
    },
    'Gelling Agent': {
        'what_it_does': 'Transforms liquids into a gel, jelly, or firm dessert texture.',
        'simple_explanation': 'A plant or animal extract (like pectin or gelatin) that solidifies liquids into spreads and desserts.',
        'regular_consumption': 'Standard food substance; safe for regular consumption in typical dietary amounts.',
    },
    'Grain': {
        'what_it_does': 'Acts as the primary carbohydrate base, offering structure, energy, and fiber.',
        'simple_explanation': 'Flour or whole kernels harvested from cereal crops (wheat, oats, corn, rice).',
        'regular_consumption': 'Wholesome staple of human diets; provides sustained energy unless you have celiac disease or grain sensitivities.',
    },
    'Humectant': {
        'what_it_does': 'Retains moisture so baked goods, candies, and snacks stay soft and do not dry out.',
        'simple_explanation': 'A water-holding substance that locks in softness and prevents staleness.',
        'regular_consumption': 'Widely used and considered safe under standard food regulations.',
    },
    'Mineral': {
        'what_it_does': 'Fortifies essential micronutrients or stabilizes food chemistry.',
        'simple_explanation': 'A dietary mineral compound (such as calcium, iron, or zinc) needed for bodily functions.',
        'regular_consumption': 'Beneficial micronutrient in dietary amounts; supports bone, blood, and cellular health.',
    },
    'Preservative': {
        'what_it_does': 'Prevents spoilage by stopping bacteria, molds, and yeast from growing.',
        'simple_explanation': 'An antimicrobial compound that keeps food fresh, safe from foodborne pathogens, and shelf-stable.',
        'regular_consumption': 'Keeps packaged food safe; some individuals with asthma or eczema may be sensitive to specific preservative classes (e.g. benzoates, sulfites).',
    },
    'Raising Agent': {
        'what_it_does': 'Releases carbon dioxide gas bubbles to make cakes, biscuits, and batters rise and become fluffy.',
        'simple_explanation': 'A baking leavener (like baking soda or baking powder) that creates light, airy textures in baked foods.',
        'regular_consumption': 'Completely standard in home baking and commercial foods; leaves harmless mineral residues.',
    },
    'Thickener': {
        'what_it_does': 'Increases thickness and body in sauces, gravies, dairy desserts, and soups.',
        'simple_explanation': 'A carbohydrate or gum extracted from seeds, seaweed, or plants to create rich textures.',
        'regular_consumption': 'Standard culinary thickening agent; safe for regular consumption.',
    },
}


def _build_raw_ingredient_assessment(item, token, is_matched, recognition_status='Recognized', percentage=None):
    """Construct child-suitability, purpose, plain explanation, and regulatory evidence for an ingredient."""
    if not is_matched or item is None:
        if recognition_status == 'OCR issue':
            return {
                'purpose': 'OCR issue — unreadable text fragment',
                'what_it_does': 'Text artifact resulting from optical character recognition error, camera blur, or package curvature.',
                'plain_explanation': f"'{token}' appears to be a distorted or illegible character fragment rather than a valid ingredient.",
                'simple_explanation': 'The scanner captured irregular symbols or unclear characters that could not be recognized as a known ingredient.',
                'known_safety_concerns': 'Unreadable scan fragment. Please inspect physical package label.',
                'child_concerns': 'Unreadable scan artifact; check physical packaging.',
                'regular_consumption_note': 'Unreadable text artifact from camera or scan.',
                'age_considerations': 'N/A',
                'child_assessment': 'Not enough information',
                'simple_status': 'OCR issue',
                'simple_badge': 'secondary',
                'allergen_info': 'Unverified',
                'sources': ['OCR verification required'],
                'is_unrecognized': True,
                'display_name': token or 'OCR Fragment',
                'ingredient_type': 'unverified',
                'common_uses': 'N/A',
                'percentage': percentage,
            }
        else:
            return {
                'purpose': 'Uncategorized / Unverified ingredient',
                'what_it_does': 'This ingredient or substance was not matched to our verified food and additive registers.',
                'plain_explanation': f"'{token}' is not yet indexed in our verified food and additive catalog.",
                'simple_explanation': f"'{token}' was not matched to standard food or additive registers. Its purity, concentration, and safety profile cannot be confirmed.",
                'known_safety_concerns': 'Insufficient data available; concentration, purity, and toxicology are unverified in local catalog.',
                'child_concerns': 'Unknown. Cannot be confirmed safe for children without complete ingredient verification.',
                'regular_consumption_note': 'Unverified substance — never assumed to be safe for regular consumption.',
                'age_considerations': 'Unknown / Insufficient information',
                'child_assessment': 'Insufficient information',
                'simple_status': 'Insufficient information',
                'simple_badge': 'secondary',
                'allergen_info': 'Unverified',
                'sources': ['Regulatory catalog check required'],
                'is_unrecognized': True,
                'display_name': token or 'Unverified Ingredient',
                'ingredient_type': 'unverified',
                'common_uses': 'Unverified in database',
                'percentage': percentage,
            }

    name = item.get('name', '').lower()
    e_num = (item.get('e_number') or '').lower().replace(' ', '')
    category = item.get('category', 'General')
    health = item.get('health_effects') or ''
    banned = item.get('banned_status', False)
    allergen_tag = item.get('allergen_tag') or ''
    itype = item.get('ingredient_type') or ('additive' if e_num else 'food')
    display_name = f"{item['name']} ({item['e_number']})" if item.get('e_number') else item['name']
    if percentage:
        display_name = f"{display_name} ({percentage})"

    # Wholesome food ingredient with rich knowledge fields
    if itype == 'food' and item.get('what_is_it'):
        safety = item.get('safety_level', 'Safe')
        if safety == 'Safe':
            status_text = 'No specific concern identified'
            badge = 'success'
        elif safety == 'Caution':
            status_text = 'Caution'
            badge = 'warning'
        else:
            status_text = 'Potential concern'
            badge = 'danger'

        allergen_info = 'None identified'
        if allergen_tag:
            allergen_info = f"Major Allergen: {allergen_tag.capitalize()} (Wholesome everyday food for non-allergic individuals; avoid if you have a diagnosed allergy)."

        sources_list = [s.strip() for s in (item.get('source_attribution') or 'FSSAI / Codex Alimentarius / ICMR-NIN').split('/')]

        return {
            'purpose': item.get('why_used') or f"{category} / Food component",
            'what_it_does': item.get('why_used') or f"Provides essential nourishment, texture, and flavor.",
            'plain_explanation': item.get('what_is_it') or f"Standard wholesome food ingredient ({item['name']}).",
            'simple_explanation': item.get('what_is_it') or f"A natural food component commonly used in everyday cooking and snacks.",
            'common_uses': item.get('common_uses') or "Daily home cooking, packaged foods, and snacks.",
            'known_safety_concerns': health or 'No specific toxicity or safety concerns identified under standard dietary intake levels.',
            'child_concerns': item.get('child_considerations') or 'Wholesome and nutritious for children in balanced portions; avoid if allergic.',
            'regular_consumption_note': item.get('regular_consumption') or 'Wholesome staple suitable for regular dietary consumption.',
            'age_considerations': 'Suitable across all standard age groups in balanced amounts.',
            'child_assessment': 'No specific concern identified from available information' if safety == 'Safe' else 'Use caution',
            'simple_status': status_text,
            'simple_badge': badge,
            'allergen_info': allergen_info,
            'sources': sources_list,
            'is_unrecognized': False,
            'display_name': display_name,
            'ingredient_type': 'food',
            'percentage': percentage,
        }

    # 1. Check Southampton Six azo dyes
    if any(dye in name or (e_num and dye == e_num) for dye in SOUTHAMPTON_DYES):
        return {
            'purpose': 'Synthetic azo dye / food coloring agent',
            'what_it_does': 'Imparts bright visual coloration to foods and drinks.',
            'plain_explanation': f"Synthetic colorant ({item.get('e_number') or item['name']}) used to impart bright coloration.",
            'simple_explanation': f"A synthetic azo food dye ({item.get('e_number') or item['name']}) derived from petroleum products.",
            'known_safety_concerns': 'Linked in the EFSA Southampton Study to increased hyperactivity and reduced attention in sensitive children. EU law requires warning label.',
            'child_concerns': 'EFSA and the UK Southampton study linked synthetic azo dyes like Tartrazine to increased hyperactivity and attention issues in sensitive children.',
            'regular_consumption_note': 'Aesthetic food coloring with no nutritional benefit; health authorities recommend limiting ultra-processed foods with synthetic dyes.',
            'age_considerations': 'Children under 12 and individuals with ADHD/hyperactivity sensitivities.',
            'child_assessment': 'Potential concern',
            'simple_status': 'Potential concern',
            'simple_badge': 'danger',
            'allergen_info': 'May provoke mild allergic reactions in aspirin-sensitive individuals.',
            'sources': ['EFSA (Regulation EC No 1333/2008)', 'UK Food Standards Agency (FSA)'],
            'is_unrecognized': False,
            'display_name': display_name,
        }

    # 2. Check Intense Non-Sugar Sweeteners
    if any(sw in name or (e_num and sw == e_num) for sw in INTENSE_SWEETENERS) or category == 'Artificial Sweetener':
        return {
            'purpose': 'Intense non-nutritive sweetener',
            'what_it_does': 'Provides intense sweetness without the caloric carbohydrates of natural sugar.',
            'plain_explanation': 'Concentrated low-calorie sugar substitute providing sweetness without caloric carbohydrates.',
            'simple_explanation': 'A concentrated artificial sweetener engineered to be hundreds of times sweeter than table sugar.',
            'known_safety_concerns': 'WHO 2023 guidance on Non-Sugar Sweeteners advises against routine intake; AAP notes potential effects on pediatric taste preference and gut microbiota. Aspartame strictly contraindicated in PKU.',
            'child_concerns': 'Pediatric guidelines (AAP, WHO) advise limiting artificial sweeteners in children under 12 to foster healthy natural taste preferences.',
            'regular_consumption_note': 'WHO 2023 guidelines recommend against using non-sugar sweeteners for long-term weight control; moderate your intake.',
            'age_considerations': 'Children under 12 (not recommended for routine dietary intake by pediatric guidelines).',
            'child_assessment': 'Use caution',
            'simple_status': 'Caution',
            'simple_badge': 'warning',
            'allergen_info': 'Contains phenylalanine if aspartame; check for metabolic conditions.',
            'sources': ['WHO Guideline on Non-Sugar Sweeteners (2023)', 'American Academy of Pediatrics (AAP)'],
            'is_unrecognized': False,
            'display_name': display_name,
        }

    # 3. Check Curing Salts / Nitrites
    if any(cs in name or (e_num and cs == e_num) for cs in CURING_SALTS):
        return {
            'purpose': 'Curing agent & antimicrobial preservative',
            'what_it_does': 'Cures processed meats, preserves pink color, and prevents harmful bacterial growth (Clostridium botulinum).',
            'plain_explanation': 'Inorganic salt used to cure meats, preserve coloration, and inhibit Clostridium botulinum.',
            'simple_explanation': 'An inorganic preservative salt traditionally added to bacon, sausages, and deli meats.',
            'known_safety_concerns': 'Can react with dietary amines to form carcinogenic nitrosamines when cooked at high heat. Infants are susceptible to methemoglobinemia from excessive nitrites.',
            'child_concerns': 'Infants and toddlers are particularly susceptible to methemoglobinemia from excessive nitrites; minimize exposure.',
            'regular_consumption_note': 'Frequent intake of cured meats with nitrites has been associated by WHO/IARC with increased colorectal health risks; eat only occasionally.',
            'age_considerations': 'Infants under 1 year and young children (minimize exposure).',
            'child_assessment': 'Use caution',
            'simple_status': 'Caution',
            'simple_badge': 'warning',
            'allergen_info': 'None direct; secondary sensitivity possible.',
            'sources': ['EFSA Panel on Food Additives (ANS)', 'WHO / FAO JECFA', 'IARC Monographs'],
            'is_unrecognized': False,
            'display_name': display_name,
        }

    # 4. Check Banned or Harmful ingredients
    if banned or item.get('safety_level') == 'Harmful':
        return {
            'purpose': f"{category} / Industrial additive",
            'what_it_does': f"{category} / Industrial additive with documented health alerts.",
            'plain_explanation': f"{item['name']} is an additive with documented toxicological concerns.",
            'simple_explanation': f"{item['name']} is an additive with documented toxicological concerns or regulatory restrictions.",
            'known_safety_concerns': health or 'Banned or restricted in food manufacturing across multiple jurisdictions due to safety concerns.',
            'child_concerns': 'Not recommended for children; documented toxicological alerts or regulatory restrictions.',
            'regular_consumption_note': 'Avoid regular consumption; restricted or banned by food safety agencies in one or more jurisdictions.',
            'age_considerations': 'All age groups, particularly vulnerable pediatric populations.',
            'child_assessment': 'Potential concern',
            'simple_status': 'Potential concern',
            'simple_badge': 'danger',
            'allergen_info': allergen_tag or 'None identified',
            'sources': ['EFSA', 'US FDA Food Additive Status Registers'],
            'is_unrecognized': False,
            'display_name': display_name,
        }

    # 5. Check Sensitizing Preservatives
    if any(p in name or (e_num and p == e_num) for p in PRESERVATIVES_SENSITIZING) or category == 'Preservative':
        return {
            'purpose': 'Antimicrobial food preservative',
            'what_it_does': 'Inhibits mold, yeast, and bacteria to prolong shelf life and prevent food spoilage.',
            'plain_explanation': 'Chemical preservative that inhibits mold, yeast, and bacterial degradation to prolong shelf stability.',
            'simple_explanation': 'A common chemical preservative that keeps packaged food safe from microbes during storage.',
            'known_safety_concerns': health or 'May provoke hives, bronchospasm, or sensitivity symptoms in children with asthma or eczema.',
            'child_concerns': 'May provoke hives, wheezing, or skin flare-ups in children sensitive to preservatives or those with asthma.',
            'regular_consumption_note': 'Regulated as safe within legal concentration limits, but sensitive individuals should consume with caution.',
            'age_considerations': 'Children with asthmatic or allergic predispositions.',
            'child_assessment': 'Use caution',
            'simple_status': 'Caution',
            'simple_badge': 'warning',
            'allergen_info': 'Known intolerance/sensitivity trigger for certain individuals.',
            'sources': ['US FDA GRAS Database', 'WHO / FAO JECFA'],
            'is_unrecognized': False,
            'display_name': display_name,
        }

    # 6. Check Major Allergens
    if allergen_tag or item.get('allergen_type'):
        tag = allergen_tag or item.get('allergen_type')
        cat_info = CATEGORY_FUNCTION_MAP.get(category, {})
        return {
            'purpose': f"{category} / Food component",
            'what_it_does': cat_info.get('what_it_does', 'Serves as a natural food component providing texture and flavor.'),
            'plain_explanation': f"Natural food substance containing recognized major allergen proteins ({tag}).",
            'simple_explanation': f"A natural food ingredient containing recognized major allergen proteins ({tag}).",
            'known_safety_concerns': f"Common childhood allergen trigger. Can provoke allergic symptoms ranging from hives to acute anaphylaxis in sensitized children.",
            'child_concerns': 'Common childhood allergen trigger; avoid if the child has diagnosed allergies.',
            'regular_consumption_note': 'Nutritious everyday food for individuals without allergies; strictly avoid if you have an allergy.',
            'age_considerations': 'Infants and sensitized children.',
            'child_assessment': 'Use caution',
            'simple_status': 'Caution',
            'simple_badge': 'warning',
            'allergen_info': f"Major Allergen: {tag.capitalize()}",
            'sources': ['US FDA Food Allergen Labeling (FASTER Act)', 'Codex Alimentarius'],
            'is_unrecognized': False,
            'display_name': display_name,
        }

    # 7. Check Added Sugars
    sugar_names = {'sugar', 'sucrose', 'glucose syrup', 'corn syrup', 'high fructose corn syrup', 'dextrose', 'maltodextrin', 'fructose', 'invert sugar'}
    if any(s in name for s in sugar_names):
        return {
            'purpose': 'Sweetener / Caloric carbohydrate',
            'what_it_does': 'Adds sweetness, moisture retention, and browning in baked goods.',
            'plain_explanation': 'Caloric carbohydrate sweetener providing quick dietary energy.',
            'simple_explanation': 'A simple caloric sugar carbohydrate providing quick energy.',
            'known_safety_concerns': 'High consumption of free sugars contributes to dental caries, weight gain, and metabolic risks.',
            'child_concerns': 'Pediatric organizations (AAP, AHA) recommend limiting added sugars in children to prevent dental cavities and metabolic issues.',
            'regular_consumption_note': 'Health authorities (WHO) recommend limiting free sugars to less than 5–10% of total daily energy intake.',
            'age_considerations': 'Children under 2 (avoid added sugars); children over 2 (limit intake).',
            'child_assessment': 'No specific concern identified from available information',
            'simple_status': 'No specific concern identified',
            'simple_badge': 'success',
            'allergen_info': 'None identified',
            'sources': ['WHO Guideline: Sugars intake for adults and children', 'American Heart Association (AHA)'],
            'is_unrecognized': False,
            'display_name': display_name,
        }

    # 8. Standard safe food ingredient / other category
    cat_info = CATEGORY_FUNCTION_MAP.get(category, {})
    what_it_does = cat_info.get('what_it_does', f"Serves as a {category.lower()} in the recipe formulation.")
    simple_explanation = cat_info.get('simple_explanation', f"A standard food ingredient ({item['name']}) commonly used in cooking and food manufacturing.")
    reg_note = cat_info.get('regular_consumption', 'Standard food ingredient considered safe for regular consumption in normal culinary amounts.')

    return {
        'purpose': f"{category} / Primary food component",
        'what_it_does': what_it_does,
        'plain_explanation': f"Standard food ingredient ({item['name']}) widely used in food preparation.",
        'simple_explanation': simple_explanation,
        'known_safety_concerns': health if health and 'excessive' in health.lower() else 'No specific toxicity or pediatric safety concerns identified under standard dietary intake levels.',
        'child_concerns': 'No specific pediatric toxicity concerns identified under standard dietary intake levels.',
        'regular_consumption_note': reg_note,
        'age_considerations': 'Suitable across all standard age groups in balanced amounts.',
        'child_assessment': 'No specific concern identified from available information',
        'simple_status': 'No specific concern identified',
        'simple_badge': 'success',
        'allergen_info': 'None identified',
        'sources': ['US FDA GRAS Notice Inventory', 'EFSA Scientific Opinions', 'WHO / FAO Codex Alimentarius'],
        'is_unrecognized': False,
        'display_name': display_name,
    }


def enrich_ingredient_details(res, item, token, is_matched, recognition_status='Recognized', percentage=None):
    """
    Enriches an ingredient assessment dictionary with precise 2-3 line descriptions,
    the 6 exact safety statuses, authoritative children's age guidance, and choking hazard notes.
    """
    if not is_matched or item is None:
        if recognition_status == 'OCR issue':
            res['short_description'] = (
                f"Distorted character fragment (\"{token}\") from optical recognition or package curve. "
                "Inspect physical packaging to verify the ingredient."
            )
            res['safety_status'] = 'Insufficient information'
            res['safety_status_badge'] = 'secondary'
            res['safety_short_explanation'] = 'Illegible character fragment; safety cannot be evaluated without clear label text.'
            res['children_suitability_status'] = 'Insufficient information to provide age-specific guidance'
            res['children_suitability_badge'] = 'secondary'
            res['children_guidance'] = 'Unreadable scan fragment. Please check physical product packaging.'
            res['age_guidance_text'] = 'No specific minimum age established from the available information.'
            res['age_brackets'] = []
            res['choking_hazard'] = False
            res['choking_hazard_note'] = ''
            res['allergen_warning'] = ''
            return res
        else:
            res['short_description'] = (
                f"An ingredient or substance (\"{token}\") that is not yet matched to our verified food registers. "
                "Its purity, concentration, and food safety profile cannot be confirmed from the local database."
            )
            res['safety_status'] = 'Insufficient information'
            res['safety_status_badge'] = 'secondary'
            res['safety_short_explanation'] = 'This substance could not be verified in official food registers. Its safety cannot be evaluated from available information.'
            res['children_suitability_status'] = 'Insufficient information to provide age-specific guidance'
            res['children_suitability_badge'] = 'secondary'
            res['children_guidance'] = 'Unknown substance; cannot be confirmed safe for children without complete ingredient verification.'
            res['age_guidance_text'] = 'No specific minimum age established from the available information.'
            res['age_brackets'] = []
            res['choking_hazard'] = False
            res['choking_hazard_note'] = ''
            res['allergen_warning'] = ''
            return res

    name_lower = (item.get('name') or '').lower()
    e_num = (item.get('e_number') or '').lower().replace(' ', '')
    category = item.get('category', 'General')
    allergen_tag = item.get('allergen_tag') or item.get('allergen_type') or ''
    health = item.get('health_effects') or ''
    banned = item.get('banned_status', False)
    safety_level = item.get('safety_level') or item.get('safety_rating') or 'Safe'
    itype = item.get('ingredient_type') or ('additive' if e_num else 'food')

    # Detect specific classes
    is_honey = 'honey' in name_lower
    is_nut = any(n in name_lower for n in ['peanut', 'groundnut', 'cashew', 'almond', 'walnut', 'pistachio', 'hazelnut', 'pecan'])
    is_dairy = any(d in name_lower for d in ['milk', 'whey', 'casein', 'cheese', 'butter', 'dairy', 'lactose'])
    is_sugar = any(s in name_lower for s in ['sugar', 'sucrose', 'glucose syrup', 'corn syrup', 'high fructose corn syrup', 'dextrose', 'invert sugar'])
    is_salt = any(s in name_lower for s in ['salt', 'sodium chloride', 'rock salt', 'black salt'])
    is_sweetener = any(sw in name_lower or (e_num and sw == e_num) for sw in INTENSE_SWEETENERS) or category == 'Artificial Sweetener'
    is_dye = any(dye in name_lower or (e_num and dye == e_num) for dye in SOUTHAMPTON_DYES)
    is_curing = any(cs in name_lower or (e_num and cs == e_num) for cs in CURING_SALTS)
    is_caffeine = any(c in name_lower for c in ['caffeine', 'coffee extract', 'guarana', 'taurine'])

    # 1. Choking Hazard
    choking_hazard = False
    choking_hazard_note = ''
    if is_nut or 'seed' in name_lower:
        if is_nut:
            choking_hazard = True
            choking_hazard_note = (
                'Whole peanuts and tree nuts are a leading cause of pediatric choking. '
                'Health agencies (AAP, NHS) advise against feeding whole nuts to children under 5 years; '
                'offer smooth nut pastes or purees instead.'
            )

    # 2. Allergen Warning
    allergen_warning = ''
    if allergen_tag:
        allergen_warning = f"Major Allergen: {allergen_tag.capitalize()}. Can provoke severe reactions in sensitized individuals."

    # 3. Children's Age Guidance & Brackets
    age_brackets = []
    if is_honey:
        child_status = 'Avoid for specific age groups or circumstances'
        child_badge = 'danger'
        child_guidance = (
            'Must not be given to infants under 12 months because of infant botulism risk (AAP, CDC, WHO, NHS). '
            'Mature digestive tracts protect children 12+ months.'
        )
        age_text = 'Avoid under 12 months (infant botulism risk). Suitable from 12+ months in culinary amounts.'
        age_brackets = [
            {'bracket': 'Below 12 months', 'status': 'Strictly Avoid', 'badge': 'danger', 'note': 'High risk of infant botulism from Clostridium botulinum spores.'},
            {'bracket': '1–2 years', 'status': 'Use in moderation', 'badge': 'warning', 'note': 'Digestive system is mature; limit added sugars.'},
            {'bracket': '2+ years', 'status': 'Generally suitable', 'badge': 'success', 'note': 'Wholesome natural sweetener in balanced amounts.'}
        ]
    elif is_nut:
        child_status = 'Use caution for certain ages'
        child_badge = 'warning'
        child_guidance = (
            'Whole nuts present a serious choking hazard for children under 5 years (AAP/NHS). '
            'Smooth nut purees are recommended from 6 months for allergy prevention under pediatric guidance.'
        )
        age_text = 'Choking hazard if whole for children under 5 years. Smooth paste suitable from 6 months under guidance.'
        age_brackets = [
            {'bracket': 'Below 6 months', 'status': 'Unsuitable', 'badge': 'danger', 'note': 'Exclusive breastmilk or infant formula is recommended.'},
            {'bracket': '6–12 months', 'status': 'Smooth paste only', 'badge': 'warning', 'note': 'Finely pureed paste recommended for early allergen introduction; NO whole nuts.'},
            {'bracket': '1–5 years', 'status': 'Choking caution', 'badge': 'warning', 'note': 'Do not offer whole or chunky nuts; spread smooth nut butter thinly.'},
            {'bracket': '5+ years', 'status': 'Generally suitable', 'badge': 'success', 'note': 'Safe for non-allergic children capable of thorough chewing.'}
        ]
    elif is_dairy:
        child_status = 'Generally suitable for children when used in ordinary food quantities'
        child_badge = 'success'
        child_guidance = (
            'Dairy used as a cooked recipe ingredient is suitable from 6 months. '
            'Fluid cow\'s milk should not replace breastmilk or infant formula as an infant\'s main drink before 12 months (AAP/WHO).'
        )
        age_text = 'Suitable as a food ingredient from 6 months. Not recommended as a primary drink before 12 months.'
        age_brackets = [
            {'bracket': 'Below 6 months', 'status': 'Unsuitable', 'badge': 'danger', 'note': 'Breastmilk or formula only.'},
            {'bracket': '6–12 months', 'status': 'Ingredient only', 'badge': 'success', 'note': 'Suitable as an ingredient in cooked complementary food; avoid as primary drink.'},
            {'bracket': '1+ years', 'status': 'Generally suitable', 'badge': 'success', 'note': 'Nutrient-rich source of dietary calcium and protein for non-allergic toddlers.'}
        ]
    elif is_sugar:
        child_status = 'Avoid for specific age groups or circumstances'
        child_badge = 'warning'
        child_guidance = (
            'Pediatric authorities (AAP, WHO, USDA 2020–2025) recommend zero added sugars for children under 2 years; '
            'strictly limit thereafter to protect dental and metabolic health.'
        )
        age_text = 'Avoid under 2 years (AAP/USDA guidelines); limit strictly for older children.'
        age_brackets = [
            {'bracket': 'Below 2 years', 'status': 'Avoid added sugars', 'badge': 'danger', 'note': 'Developing taste preferences should not be conditioned to high sweetness.'},
            {'bracket': '2–5 years', 'status': 'Limit strictly', 'badge': 'warning', 'note': 'Limit free sugars to less than 25g (6 teaspoons) per day.'},
            {'bracket': '5+ years', 'status': 'Moderate intake', 'badge': 'warning', 'note': 'Limit intake to prevent dental cavities and metabolic disruption.'}
        ]
    elif is_salt:
        child_status = 'Use caution for certain ages'
        child_badge = 'warning'
        child_guidance = (
            'Infants under 12 months have immature kidneys that cannot excrete high sodium (<1g salt/day recommended by NHS and EFSA); '
            'limit added salt in toddlers.'
        )
        age_text = 'Limit under 12 months (<1g salt/day). Restrict in toddlers and young children.'
        age_brackets = [
            {'bracket': 'Below 12 months', 'status': 'Avoid added salt', 'badge': 'danger', 'note': 'Immature infant kidneys cannot handle salt (<1g salt/day max).'},
            {'bracket': '1–3 years', 'status': 'Limit to <2g/day', 'badge': 'warning', 'note': 'Toddlers should consume no more than 2g salt (0.8g sodium) per day.'},
            {'bracket': '4+ years', 'status': 'Standard balance', 'badge': 'success', 'note': 'Moderate culinary seasoning within balanced daily guidelines.'}
        ]
    elif is_sweetener:
        child_status = 'Avoid for specific age groups or circumstances'
        child_badge = 'warning'
        child_guidance = (
            'WHO 2023 guidance and AAP advise against routine use of non-sugar sweeteners in children. '
            'Aspartame contains phenylalanine and is hazardous in Phenylketonuria (PKU).'
        )
        age_text = 'Not recommended for routine intake in children under 12 years (WHO 2023 / AAP).'
        age_brackets = [
            {'bracket': 'Under 12 years', 'status': 'Not recommended', 'badge': 'warning', 'note': 'Non-sugar sweeteners are not advised for pediatric weight control or routines.'},
            {'bracket': 'PKU Patients', 'status': 'Strictly Contraindicated', 'badge': 'danger', 'note': 'Aspartame contains phenylalanine.'}
        ]
    elif is_dye:
        child_status = 'Use caution for certain ages'
        child_badge = 'warning'
        child_guidance = (
            'EFSA and UK Southampton studies linked synthetic azo dyes to increased hyperactivity and attention issues in sensitive children. '
            'EU law mandates a cautionary label.'
        )
        age_text = 'Use caution for children under 12 years, especially those with ADHD or hyperactivity tendencies.'
        age_brackets = [
            {'bracket': 'Children under 12', 'status': 'Use Caution', 'badge': 'warning', 'note': 'May adversely affect activity and attention in sensitive children.'}
        ]
    elif is_curing:
        child_status = 'Avoid for specific age groups or circumstances'
        child_badge = 'danger'
        child_guidance = (
            'Infants and young toddlers are particularly susceptible to methemoglobinemia from nitrites; '
            'minimize exposure (EFSA/AAP).'
        )
        age_text = 'Avoid for infants under 1 year and toddlers.'
        age_brackets = [
            {'bracket': 'Under 1 year', 'status': 'Strictly Avoid', 'badge': 'danger', 'note': 'Risk of infant methemoglobinemia.'},
            {'bracket': 'Toddlers', 'status': 'Minimize exposure', 'badge': 'warning', 'note': 'Limit intake of cured processed meats.'}
        ]
    elif is_caffeine:
        child_status = 'Avoid for specific age groups or circumstances'
        child_badge = 'danger'
        child_guidance = (
            'American Academy of Pediatrics (AAP) recommends that children under 12 avoid caffeine and energy drinks entirely.'
        )
        age_text = 'Avoid under 12 years; limit for adolescents (AAP).'
        age_brackets = [
            {'bracket': 'Under 12 years', 'status': 'Strictly Avoid', 'badge': 'danger', 'note': 'Risk of elevated heart rate, sleep disruption, and anxiety.'},
            {'bracket': 'Teenagers', 'status': 'Limit intake', 'badge': 'warning', 'note': 'Monitor total daily caffeine consumption.'}
        ]
    elif banned or safety_level == 'Harmful':
        child_status = 'Avoid for specific age groups or circumstances'
        child_badge = 'danger'
        child_guidance = 'Not recommended for children; documented toxicological concerns or regulatory restrictions.'
        age_text = 'Avoid across all pediatric age groups.'
        age_brackets = []
    elif itype == 'food':
        child_status = 'Generally suitable for children when used in ordinary food quantities'
        child_badge = 'success'
        child_guidance = (
            item.get('child_considerations') or
            'Wholesome food ingredient suitable for children when prepared in an age-appropriate texture and balanced portion.'
        )
        age_text = 'No specific minimum age established from the available information.'
        age_brackets = []
    else:
        # Additive
        child_status = 'Generally suitable for children when used in ordinary food quantities' if safety_level == 'Safe' else 'Use caution for certain ages'
        child_badge = 'success' if safety_level == 'Safe' else 'warning'
        child_guidance = 'Consider the complete product and age-specific dietary guidance. No universal minimum age can be determined from this ingredient alone.'
        age_text = 'No specific minimum age established from the available information.'
        age_brackets = []

    # 4. Safety Assessment Status & Short Explanation
    if is_honey:
        safety_status = 'Avoid for specific groups'
        safety_badge = 'danger'
        safety_exp = 'Strictly unsafe for infants under 12 months due to botulism risk; safe for older children and adults in moderation.'
    elif is_caffeine:
        safety_status = 'Avoid for specific groups'
        safety_badge = 'danger'
        safety_exp = 'Stimulant substance not suitable for young children, pregnant women, or caffeine-sensitive individuals.'
    elif banned or safety_level == 'Harmful':
        safety_status = 'Potential concern'
        safety_badge = 'danger'
        safety_exp = 'Documented toxicological alerts or regulatory restrictions across food safety authorities.'
    elif is_dye:
        safety_status = 'Potential concern'
        safety_badge = 'danger'
        safety_exp = 'Purely aesthetic synthetic colorant with documented hyperactivity alerts in sensitive children.'
    elif is_curing:
        safety_status = 'Potential concern'
        safety_badge = 'danger'
        safety_exp = 'Can form nitrosamines when cooked at high heat; infants are vulnerable to methemoglobinemia.'
    elif is_sweetener or is_sugar:
        safety_status = 'Use caution'
        safety_badge = 'warning'
        safety_exp = 'Safe in moderation; frequent or excessive intake should be limited in a balanced diet.'
    elif safety_level == 'Caution' or category == 'Preservative':
        safety_status = 'Use caution'
        safety_badge = 'warning'
        safety_exp = 'Approved within legal limits; sensitive individuals with asthma or allergies should monitor intake.'
    elif allergen_tag:
        safety_status = 'Potential concern'
        safety_badge = 'warning'
        safety_exp = f"Recognized major food allergen ({allergen_tag.capitalize()}). Avoid if you have a diagnosed allergy."
    elif itype == 'food':
        safety_status = 'No specific concern identified'
        safety_badge = 'success'
        safety_exp = 'Standard wholesome dietary ingredient with established history of safe human consumption.'
    else:
        safety_status = 'Generally recognized for its intended food use'
        safety_badge = 'primary'
        safety_exp = 'Approved food additive evaluated as safe within intended culinary use levels by international food safety bodies.'

    # 5. Short Description: Strictly 2-3 short lines in simple everyday English
    if item.get('what_is_it') and item.get('why_used'):
        desc1 = item.get('what_is_it').strip()
        desc2 = item.get('why_used').strip()
        action_verb = desc2[:1].lower() + desc2[1:] if not desc2.startswith('Used') else desc2
        short_desc = f"{desc1} It is used in food preparation to {action_verb}."
        words = short_desc.split()
        if len(words) > 35:
            short_desc = ' '.join(words[:32]) + '...'
    elif itype == 'food':
        short_desc = (
            f"A natural culinary ingredient ({item['name']}) commonly used in everyday cooking and packaged foods. "
            "It provides flavor, texture, and nutritional value in balanced meals."
        )
    elif e_num:
        short_desc = (
            f"An approved food additive ({item['name']}, {item['e_number']}) classified as a {category.lower()}. "
            "It is added during manufacturing to help maintain consistent food quality and texture."
        )
    else:
        short_desc = (
            f"A standard food substance ({item['name']}) classified under {category.lower()}. "
            "It is used in commercial food preparation to achieve desired taste and stability."
        )

    res['short_description'] = short_desc
    res['safety_status'] = safety_status
    res['safety_status_badge'] = safety_badge
    res['safety_short_explanation'] = safety_exp
    res['children_suitability_status'] = child_status
    res['children_suitability_badge'] = child_badge
    res['children_guidance'] = child_guidance
    res['age_guidance_text'] = age_text
    res['age_brackets'] = age_brackets
    res['choking_hazard'] = choking_hazard
    res['choking_hazard_note'] = choking_hazard_note
    res['allergen_warning'] = allergen_warning

    return res


def build_ingredient_assessment(item, token, is_matched, recognition_status='Recognized', percentage=None):
    """Construct complete ingredient details with 2-3 line plain-English descriptions and children's age guidance."""
    raw = _build_raw_ingredient_assessment(item, token, is_matched, recognition_status, percentage)
    return enrich_ingredient_details(raw, item, token, is_matched, recognition_status, percentage)


def generate_product_age_breakdown(detected_list, raw_text="", is_cosmetic=False):
    """
    Generates dynamic product-level assessment across 6 pediatric age groups:
    - Under 6 months
    - 6–12 months
    - 1–2 years
    - 2–5 years
    - 5–12 years
    - Teenagers
    Based on actual scanned ingredients, allergens, choking hazards, sugar, salt, and additives.
    """
    if is_cosmetic:
        return [
            {
                'age_group': 'Under 6 months',
                'assessment': 'Unsuitable (Cosmetic product)',
                'badge_class': 'danger',
                'guidance': 'Topical cosmetic item strictly for external use. Keep out of reach of infants.'
            },
            {
                'age_group': '6–12 months',
                'assessment': 'Unsuitable (Cosmetic product)',
                'badge_class': 'danger',
                'guidance': 'Topical cosmetic item strictly for external use. Not for oral consumption.'
            },
            {
                'age_group': '1–2 years',
                'assessment': 'Unsuitable (Cosmetic product)',
                'badge_class': 'danger',
                'guidance': 'Topical product. Prevent accidental ingestion or contact with eyes/mouth.'
            },
            {
                'age_group': '2–5 years',
                'assessment': 'Unsuitable (Cosmetic product)',
                'badge_class': 'danger',
                'guidance': 'Formulated strictly for external skin/hair use. Not for consumption.'
            },
            {
                'age_group': '5–12 years',
                'assessment': 'External use only',
                'badge_class': 'warning',
                'guidance': 'Topical personal care product. Use only as directed on packaging.'
            },
            {
                'age_group': 'Teenagers',
                'assessment': 'External use only',
                'badge_class': 'secondary',
                'guidance': 'Topical personal care product. Check ingredients for skin sensitivities.'
            }
        ]

    if not detected_list:
        return [
            {
                'age_group': 'Under 6 months',
                'assessment': 'Unsuitable as complementary food',
                'badge_class': 'danger',
                'guidance': 'Exclusive breastfeeding or infant formula is universally recommended by WHO/AAP.'
            },
            {
                'age_group': '6–12 months',
                'assessment': 'Insufficient information',
                'badge_class': 'secondary',
                'guidance': 'No ingredients were detected to evaluate age suitability. Verify packaging.'
            },
            {
                'age_group': '1–2 years',
                'assessment': 'Insufficient information',
                'badge_class': 'secondary',
                'guidance': 'No ingredients were detected to evaluate age suitability. Verify packaging.'
            },
            {
                'age_group': '2–5 years',
                'assessment': 'Insufficient information',
                'badge_class': 'secondary',
                'guidance': 'No ingredients were detected to evaluate age suitability. Verify packaging.'
            },
            {
                'age_group': '5–12 years',
                'assessment': 'Insufficient information',
                'badge_class': 'secondary',
                'guidance': 'No ingredients were detected to evaluate age suitability. Verify packaging.'
            },
            {
                'age_group': 'Teenagers',
                'assessment': 'Insufficient information',
                'badge_class': 'secondary',
                'guidance': 'No ingredients were detected to evaluate age suitability. Verify packaging.'
            }
        ]

    has_honey = False
    has_nuts = False
    has_dairy = False
    has_sugar = False
    has_salt = False
    has_sweeteners = False
    has_dyes = False
    has_curing = False
    has_caffeine = False
    allergens = set()
    unverified_count = 0

    for ing in detected_list:
        name_l = (ing.get('matched_name') or ing.get('name') or ing.get('raw_token') or '').lower()
        cat = (ing.get('category') or '').lower()
        tag = ing.get('allergen_tag') or ing.get('allergen_type')
        if tag:
            allergens.add(tag)
        if ing.get('is_unrecognized') or ing.get('recognition_status') in ('Unidentified', 'OCR issue'):
            unverified_count += 1

        if 'honey' in name_l:
            has_honey = True
        if any(n in name_l for n in ['peanut', 'groundnut', 'cashew', 'almond', 'walnut', 'pistachio', 'hazelnut', 'pecan']) or ing.get('choking_hazard'):
            has_nuts = True
        if any(d in name_l for d in ['milk', 'whey', 'casein', 'cheese', 'butter']):
            has_dairy = True
        if any(s in name_l for s in ['sugar', 'sucrose', 'glucose syrup', 'corn syrup', 'dextrose', 'invert sugar']):
            has_sugar = True
        if any(s in name_l for s in ['salt', 'sodium chloride']):
            has_salt = True
        if any(sw in name_l for sw in INTENSE_SWEETENERS) or 'sweetener' in cat:
            has_sweeteners = True
        if any(dye in name_l for dye in SOUTHAMPTON_DYES) or 'colour' in cat or 'color' in cat:
            has_dyes = True
        if any(cs in name_l for cs in CURING_SALTS):
            has_curing = True
        if any(c in name_l for c in ['caffeine', 'coffee extract', 'guarana', 'taurine']):
            has_caffeine = True

    # 1. Under 6 months
    u6m = {
        'age_group': 'Under 6 months',
        'assessment': 'Unsuitable as complementary food',
        'badge_class': 'danger',
        'guidance': 'Exclusive breastfeeding or infant formula is universally recommended by WHO and AAP for infants under 6 months. Packaged solid foods and snacks must not be given.'
    }

    # 2. 6–12 months
    if has_honey:
        m6_12 = {
            'age_group': '6–12 months',
            'assessment': 'Avoid (Honey botulism risk)',
            'badge_class': 'danger',
            'guidance': 'Contains honey, which carries a severe risk of Clostridium botulinum spore toxicity causing infant botulism in children under 12 months (AAP, CDC, NHS).'
        }
    elif has_curing:
        m6_12 = {
            'age_group': '6–12 months',
            'assessment': 'Avoid (Curing salts/Nitrites)',
            'badge_class': 'danger',
            'guidance': 'Contains curing salts / nitrites. Infants under 1 year are susceptible to methemoglobinemia from nitrite exposure (EFSA/AAP).'
        }
    elif has_nuts:
        m6_12 = {
            'age_group': '6–12 months',
            'assessment': 'Avoid whole nuts (Choking hazard)',
            'badge_class': 'warning',
            'guidance': 'Contains peanuts or tree nuts. Whole nuts are a major choking hazard under 5 years (AAP/NHS). Smooth purees only if introducing single allergens under pediatric advice.'
        }
    elif has_sugar or has_salt:
        m6_12 = {
            'age_group': '6–12 months',
            'assessment': 'Not recommended (Added salt/sugar)',
            'badge_class': 'warning',
            'guidance': 'Zero added salt or sugar is advised under 12 months (NHS, WHO, AAP) to protect immature kidneys and developing taste preferences.'
        }
    elif has_sweeteners or has_dyes:
        m6_12 = {
            'age_group': '6–12 months',
            'assessment': 'Not recommended (Ultra-processed additives)',
            'badge_class': 'warning',
            'guidance': 'Contains artificial sweeteners or synthetic dyes not suitable for infant complementary feeding.'
        }
    elif allergens:
        m6_12 = {
            'age_group': '6–12 months',
            'assessment': 'Suitable with allergen precautions',
            'badge_class': 'warning',
            'guidance': f"Contains major allergens ({', '.join(sorted(allergens))}). Introduce allergens one at a time and monitor for allergic reactions."
        }
    else:
        m6_12 = {
            'age_group': '6–12 months',
            'assessment': 'Suitable if texture is age-appropriate',
            'badge_class': 'success',
            'guidance': 'Ingredients are standard dietary components. Ensure food texture is smoothly pureed or mashed to prevent choking.'
        }

    # 3. 1–2 years (Toddlers)
    if has_curing:
        y1_2 = {
            'age_group': '1–2 years',
            'assessment': 'Limit strictly (Curing salts)',
            'badge_class': 'danger',
            'guidance': 'Young toddlers are susceptible to nitrite additives; minimize exposure to cured processed meats.'
        }
    elif has_nuts:
        y1_2 = {
            'age_group': '1–2 years',
            'assessment': 'Caution: Choking risk if whole nuts',
            'badge_class': 'warning',
            'guidance': 'Whole nuts and hard chunks present a serious choking hazard for toddlers under 5 years (AAP/NHS). Offer only as smooth nut butter spread thinly.'
        }
    elif has_sugar:
        y1_2 = {
            'age_group': '1–2 years',
            'assessment': 'Limit strictly (Added sugar)',
            'badge_class': 'warning',
            'guidance': 'AAP and USDA Dietary Guidelines recommend avoiding added sugars for children under 2 years to protect oral health and prevent obesity.'
        }
    elif has_sweeteners or has_dyes:
        y1_2 = {
            'age_group': '1–2 years',
            'assessment': 'Use caution (Synthetic additives)',
            'badge_class': 'warning',
            'guidance': 'Contains non-nutritive additives not recommended for routine intake in toddlers by WHO/AAP.'
        }
    elif allergens:
        y1_2 = {
            'age_group': '1–2 years',
            'assessment': 'Suitable if no diagnosed allergy',
            'badge_class': 'success',
            'guidance': f"Check declared allergens ({', '.join(sorted(allergens))}) against child's dietary profile."
        }
    else:
        y1_2 = {
            'age_group': '1–2 years',
            'assessment': 'Generally suitable based on available information',
            'badge_class': 'success',
            'guidance': 'Wholesome composition suitable for toddler diets in age-appropriate portions.'
        }

    # 4. 2–5 years (Preschool)
    if has_nuts:
        y2_5 = {
            'age_group': '2–5 years',
            'assessment': 'Caution: Supervise whole nuts',
            'badge_class': 'warning',
            'guidance': 'Children under 5 remain at elevated risk of choking on whole peanuts or tree nuts (AAP/NHS). Supervise chewing or choose smooth alternatives.'
        }
    elif has_dyes:
        y2_5 = {
            'age_group': '2–5 years',
            'assessment': 'Use caution (Synthetic food dyes)',
            'badge_class': 'warning',
            'guidance': 'Contains synthetic azo dyes linked to hyperactivity and attention difficulties in sensitive children (EFSA).'
        }
    elif has_sweeteners:
        y2_5 = {
            'age_group': '2–5 years',
            'assessment': 'Limit consumption (Artificial sweeteners)',
            'badge_class': 'warning',
            'guidance': 'WHO 2023 guidance advises against using non-sugar sweeteners for routine intake in children.'
        }
    elif allergens:
        y2_5 = {
            'age_group': '2–5 years',
            'assessment': 'Suitable if no diagnosed allergy',
            'badge_class': 'success',
            'guidance': f"Check declared allergens ({', '.join(sorted(allergens))}) for sensitive children."
        }
    else:
        y2_5 = {
            'age_group': '2–5 years',
            'assessment': 'Generally suitable based on available information',
            'badge_class': 'success',
            'guidance': 'Suitable as part of a varied, balanced preschool diet in moderate portions.'
        }

    # 5. 5–12 years (School Age)
    if has_caffeine:
        y5_12 = {
            'age_group': '5–12 years',
            'assessment': 'Avoid (Caffeine content)',
            'badge_class': 'danger',
            'guidance': 'Children under 12 should avoid caffeine and stimulant ingredients due to elevated heart rate and sleep disruption (AAP).'
        }
    elif has_dyes:
        y5_12 = {
            'age_group': '5–12 years',
            'assessment': 'Use caution (Synthetic dyes)',
            'badge_class': 'warning',
            'guidance': 'May affect attention and activity levels in children sensitive to synthetic food dyes (ADHD considerations).'
        }
    elif allergens:
        y5_12 = {
            'age_group': '5–12 years',
            'assessment': 'Suitable if no diagnosed allergy',
            'badge_class': 'success',
            'guidance': f"Check school lunch allergy guidelines regarding declared allergens: {', '.join(sorted(allergens))}."
        }
    else:
        y5_12 = {
            'age_group': '5–12 years',
            'assessment': 'Generally suitable based on available information',
            'badge_class': 'success',
            'guidance': 'Standard dietary profile suitable within daily school-age nutritional recommendations.'
        }

    # 6. Teenagers (13+ years)
    if has_caffeine:
        teen = {
            'age_group': 'Teenagers',
            'assessment': 'Suitable with caution (Caffeine)',
            'badge_class': 'warning',
            'guidance': 'Monitor total daily caffeine consumption across all foods and beverages.'
        }
    elif allergens:
        teen = {
            'age_group': 'Teenagers',
            'assessment': 'Suitable if no diagnosed allergy',
            'badge_class': 'success',
            'guidance': f"Nutritious dietary option; verify declared allergens ({', '.join(sorted(allergens))})."
        }
    else:
        teen = {
            'age_group': 'Teenagers',
            'assessment': 'Generally suitable based on available information',
            'badge_class': 'success',
            'guidance': 'Appropriate for regular inclusion in an active, balanced adolescent diet.'
        }

    return [u6m, m6_12, y1_2, y2_5, y5_12, teen]


def evaluate_child_suitability(detected_list, raw_text=""):
    """Evaluate overall child suitability for the scanned product based on verified ingredient evidence."""
    if not detected_list:
        return {
            'status': 'Insufficient information',
            'simple_status': 'Not enough information',
            'badge_class': 'secondary',
            'summary': 'No ingredients were detected to evaluate child suitability.',
            'key_factors': ['No readable ingredient text available.'],
            'age_guidance': 'Please upload or enter a readable ingredient list.',
            'is_cosmetic': False,
            'disclaimer': 'Disclaimer: IngredientIQ provides informational guidance compiled from public scientific sources (EFSA, FDA, WHO, AAP). It does not substitute for professional pediatric or medical advice.',
            'age_breakdown': generate_product_age_breakdown([], raw_text),
        }

    lower_text = (raw_text or '').lower()
    is_cosmetic = any(term in lower_text for term in ['shampoo', 'lotion', 'body wash', 'conditioner', 'apply to skin', 'for external use only', 'eau de parfum', 'cosmetic'])
    if not is_cosmetic:
        for ing in detected_list:
            if ing.get('category') == 'Cosmetic' or any(c in ing.get('matched_name', '').lower() for c in COSMETIC_INDICATORS):
                is_cosmetic = True
                break

    if is_cosmetic:
        return {
            'status': 'Not for ingestion (Cosmetic / Topical product)',
            'simple_status': 'Not for ingestion (Cosmetic product)',
            'badge_class': 'danger',
            'summary': 'This product contains topical cosmetic substances. It is strictly formulated for external skin/hair use and is not safe for oral consumption by children or adults.',
            'key_factors': ['Product is identified as a topical cosmetic, personal care, or non-food item.'],
            'age_guidance': 'Keep out of reach of infants and unsupervised young children to prevent accidental ingestion.',
            'is_cosmetic': True,
            'disclaimer': 'Disclaimer: IngredientIQ provides informational guidance compiled from public scientific sources (EFSA, FDA, WHO, AAP). It does not substitute for professional pediatric or medical advice.',
            'age_breakdown': generate_product_age_breakdown(detected_list, raw_text, is_cosmetic=True),
        }

    concerns = []
    cautions = []
    allergens = []
    unrecognized = []

    for ing in detected_list:
        ca = ing.get('child_assessment')
        name = ing.get('matched_name') or ing.get('raw_token')
        if ca == 'Potential concern':
            concerns.append(f"{name}: {ing.get('known_safety_concerns', 'Safety concern identified')}")
        elif ca == 'Use caution':
            cautions.append(f"{name}: {ing.get('known_safety_concerns', 'Caution advised')}")
        elif ca == 'Insufficient information' or ing.get('is_unrecognized'):
            unrecognized.append(name)
        if ing.get('allergen_type') or ing.get('allergen_tag'):
            tag = ing.get('allergen_type') or ing.get('allergen_tag')
            if tag not in allergens:
                allergens.append(tag)

    total = len(detected_list)
    unrec_ratio = len(unrecognized) / max(total, 1)

    if concerns:
        status = 'Potential concern'
        simple_status = 'Potential concern'
        badge_class = 'danger'
        summary = 'One or more ingredients have documented pediatric safety considerations (e.g. synthetic azo dyes, banned additives, or high-risk substances). Review carefully before offering to young children.'
        age_guidance = 'Not recommended for regular consumption by infants, toddlers, or children sensitive to artificial food dyes or stimulants.'
    elif cautions:
        status = 'Use caution'
        simple_status = 'Use caution'
        badge_class = 'warning'
        summary = 'Product contains ingredients that warrant parental caution, such as intense non-sugar sweeteners, preservatives, or major childhood allergens.'
        age_guidance = 'Consume in moderation; check allergen tags if the child has diagnosed food allergies.'
    elif unrec_ratio >= 0.4:
        status = 'Insufficient information'
        simple_status = 'Not enough information'
        badge_class = 'secondary'
        summary = f'{len(unrecognized)} out of {total} ingredients on this label could not be verified in the database. Suitability cannot be confirmed without complete ingredient data.'
        age_guidance = 'Verify unverified substances on physical manufacturer packaging.'
    else:
        status = 'No specific concern identified from available information'
        simple_status = 'No specific concern identified'
        badge_class = 'success'
        summary = 'Based on available regulatory literature (EFSA, FDA, WHO), identified ingredients consist of standard food substances without specific pediatric alerts.'
        age_guidance = 'Suitable for general family consumption within balanced dietary habits.'

    factors = []
    if concerns:
        factors.extend(concerns)
    if cautions:
        factors.extend(cautions)
    if allergens:
        factors.append(f"Contains major childhood allergens: {', '.join(allergens)}.")
    if unrecognized:
        factors.append(f"Unverified ingredients ({len(unrecognized)}): {', '.join(unrecognized[:4])}{'...' if len(unrecognized) > 4 else ''}.")
    if not factors:
        factors.append('All detected ingredients are standard dietary components with established safety histories.')

    return {
        'status': status,
        'simple_status': simple_status,
        'badge_class': badge_class,
        'summary': summary,
        'key_factors': factors,
        'age_guidance': age_guidance,
        'is_cosmetic': False,
        'disclaimer': 'Disclaimer: IngredientIQ provides informational guidance compiled from public scientific sources (EFSA, FDA, WHO, AAP). It does not substitute for professional pediatric or medical advice.',
        'age_breakdown': generate_product_age_breakdown(detected_list, raw_text, is_cosmetic=False),
    }


def evaluate_regular_consumption(detected_list, raw_text=""):
    """Evaluate whether regular daily/frequent consumption is advisable based on additive and nutritional factors."""
    if not detected_list:
        return {
            'question': 'Can I consume or use this product regularly?',
            'status': 'Insufficient information',
            'simple_status': 'Not enough information',
            'badge_class': 'secondary',
            'summary': 'No ingredient information available to assess regular consumption.',
            'key_factors': ['Ingredient list was empty.'],
            'suggestions': ['Upload or paste a complete ingredient list.'],
            'limitations_note': 'Nutritional quantities were not provided on the label.'
        }

    lower_text = (raw_text or '').lower()
    is_cosmetic = any(term in lower_text for term in ['shampoo', 'lotion', 'body wash', 'conditioner', 'apply to skin', 'for external use only', 'cosmetic'])
    if not is_cosmetic:
        for ing in detected_list:
            if ing.get('category') == 'Cosmetic' or any(c in ing.get('matched_name', '').lower() for c in COSMETIC_INDICATORS):
                is_cosmetic = True
                break

    if is_cosmetic:
        return {
            'question': 'Can I consume or use this product regularly?',
            'status': 'External use only (Cosmetic)',
            'simple_status': 'External use only (Cosmetic)',
            'badge_class': 'secondary',
            'summary': 'This product is intended strictly for external/topical application. Follow package directions for usage frequency.',
            'key_factors': ['Non-food topical formulation.'],
            'suggestions': ['Do not ingest or consume.', 'Perform a patch test before first topical use if you have sensitive skin.'],
            'limitations_note': 'Topical safety profile depends on individual dermatological sensitivity.'
        }

    # Evaluate food factors
    sugar_flags = []
    sodium_flags = []
    additive_count = 0
    synthetic_items = []
    trans_fats = []
    harmful_items = []

    sugar_names = {'sugar', 'sucrose', 'glucose syrup', 'corn syrup', 'high fructose corn syrup', 'dextrose', 'maltodextrin', 'fructose', 'invert sugar'}

    for idx, ing in enumerate(detected_list):
        name = (ing.get('matched_name') or ing.get('raw_token') or '').lower()
        cat = ing.get('category', '')
        safety = ing.get('safety_level') or ing.get('safety_rating')

        # Trans fat check
        if 'hydrogenated' in name or 'trans fat' in name:
            trans_fats.append(ing.get('matched_name', name))

        # Harmful / banned check
        if safety == 'Harmful' or ing.get('banned_status'):
            harmful_items.append(ing.get('matched_name', name))

        # Sugar in top ingredients (first 3 ingredients represent highest weight concentration in foods)
        if any(s in name for s in sugar_names):
            if idx < 3:
                sugar_flags.append(f"{ing.get('matched_name', name)} (listed among primary ingredients #{idx + 1})")
            else:
                sugar_flags.append(ing.get('matched_name', name))

        # Sodium / curing salts
        if 'salt' in name or 'sodium' in name:
            if any(cs in name for cs in CURING_SALTS):
                sodium_flags.append(f"{ing.get('matched_name', name)} (curing salt)")

        # Count synthetic additives (colors, sweeteners, preservatives)
        if cat in ['Food Colour', 'Artificial Sweetener', 'Preservative', 'Flavour Enhancer']:
            additive_count += 1
            synthetic_items.append(ing.get('matched_name', name))

    factors = []
    suggestions = []

    if trans_fats:
        factors.append(f"Contains industrial trans-fat source ({', '.join(trans_fats)}). WHO recommends avoiding industrial trans fats completely.")
        suggestions.append("Avoid products with partially hydrogenated oils; replace with foods prepared with unhydrogenated vegetable or olive oils.")

    if harmful_items:
        factors.append(f"Contains high-risk or restricted additives ({', '.join(harmful_items)}).")
        suggestions.append("Select cleaner alternatives that do not contain banned or restricted food additives.")

    if sugar_flags:
        factors.append(f"Contains added sweeteners/sugars: {', '.join(sugar_flags[:3])}. WHO guidelines recommend limiting free sugars to under 5–10% of total daily energy intake.")
        suggestions.append("Limit portion size or frequency; choose fresh fruit or unsweetened snacks for daily snacking.")

    if sodium_flags:
        factors.append(f"Contains curing salts or concentrated sodium compounds ({', '.join(sodium_flags)}).")
        suggestions.append("Balance dietary sodium by pairing with potassium-rich fresh vegetables and whole grains.")

    if additive_count >= 3:
        factors.append(f"High additive density ({additive_count} synthetic additives/preservatives/colors: {', '.join(synthetic_items[:4])}). Characteristics of ultra-processed food.")
        suggestions.append("Limit frequency of ultra-processed foods; incorporate more whole, minimally processed ingredients into daily meals.")

    # Determine status
    if trans_fats or harmful_items:
        status = 'Limit frequency'
        simple_status = 'Better to limit'
        badge_class = 'danger'
        summary = 'Regular consumption is not advisable due to the presence of industrial trans fats or restricted additives with known health risks.'
    elif (len(sugar_flags) > 0 and 'primary' in str(sugar_flags)) or additive_count >= 3 or sodium_flags:
        status = 'Limit frequency'
        simple_status = 'Better to limit'
        badge_class = 'warning'
        summary = 'Limit frequency of consumption. This product exhibits high added sugar, curing salts, or elevated additive density characteristic of ultra-processed foods.'
    elif any(ing.get('is_unrecognized') for ing in detected_list) and len([i for i in detected_list if i.get('is_unrecognized')]) / len(detected_list) >= 0.5:
        status = 'Insufficient information'
        simple_status = 'Not enough information'
        badge_class = 'secondary'
        summary = 'A majority of listed ingredients could not be verified in the database, and quantitative nutritional data is absent.'
        suggestions.append('Consult complete product packaging for full nutrition facts.')
    else:
        status = 'Generally reasonable for regular consumption based on the available information'
        simple_status = 'Generally reasonable based on available information'
        badge_class = 'success'
        summary = 'Based on the ingredient list, this product contains standard food components without excessive synthetic additive density. Appropriate for regular inclusion in a balanced diet.'
        suggestions.append('Maintain a varied diet rich in whole foods, fiber, and adequate hydration.')

    if not factors:
        factors.append('Contains standard food ingredients with no high-risk additive concentration flagged.')

    return {
        'question': 'Can I consume or use this product regularly?',
        'status': status,
        'simple_status': simple_status,
        'badge_class': badge_class,
        'summary': summary,
        'key_factors': factors,
        'suggestions': suggestions,
        'limitations_note': 'Note: Regular consumption assessment evaluates ingredient presence and sequencing. Exact quantitative values (grams of sugar, sodium, and saturated fat per serving) require the full Nutrition Facts panel.'
    }


def evaluate_watch_outs(detected_list, flagged_allergens=None, personal_conflicts=None, sections=None, unrecognized_count=0):
    """
    Card 3 Assessment: Summarize the most relevant concerns to watch out for:
    - Declared allergens
    - High sugar / salt levels (especially when listed among primary ingredients)
    - Ingredients requiring moderation or caution (sweeteners, dyes, preservatives, curing salts)
    - Personal conflicts
    - Unverified ingredients
    - If clear, state no specific high-priority concerns were identified without claiming absolute safety.
    """
    flagged_allergens = flagged_allergens or []
    personal_conflicts = personal_conflicts or []
    sections = sections or {}

    watch_items = []
    has_high_concern = False
    has_moderate_concern = False

    # 1. Personal conflicts
    if personal_conflicts:
        has_high_concern = True
        for c in personal_conflicts:
            watch_items.append({
                'category': 'Personal Conflict',
                'severity': 'danger',
                'text': c.get('message') or f"Conflicts with personal preference: {c.get('ingredient')}"
            })

    # 2. Declared / flagged allergens
    if flagged_allergens:
        has_moderate_concern = True
        conflict_tags = [c.get('tag', '').lower() for c in personal_conflicts if c.get('tag')]
        is_direct_allergen_conflict = any(a.lower() in conflict_tags for a in flagged_allergens)
        watch_items.append({
            'category': 'Allergens',
            'severity': 'danger' if is_direct_allergen_conflict else 'warning',
            'text': f"Contains recognized allergens: {', '.join(flagged_allergens)}."
        })

    # 3. Packaging warnings / allergen traces
    if sections.get('may_contain'):
        has_moderate_concern = True
        watch_items.append({
            'category': 'Cross-Contamination',
            'severity': 'warning',
            'text': f"Label states 'May contain': {sections['may_contain']}."
        })
    if sections.get('warnings'):
        has_moderate_concern = True
        watch_items.append({
            'category': 'Package Warning',
            'severity': 'warning',
            'text': f"Label advisory: {sections['warnings']}."
        })

    # 4. Harmful / banned ingredients
    harmfuls = [i.get('matched_name') for i in detected_list if i.get('safety_level') == 'Harmful' or i.get('banned_status')]
    if harmfuls:
        has_high_concern = True
        watch_items.append({
            'category': 'High-Risk Additives',
            'severity': 'danger',
            'text': f"Contains restricted or high-risk additives: {', '.join(harmfuls)}."
        })

    # 5. Southampton dyes
    dyes = [
        i.get('matched_name') for i in detected_list
        if any(d in (i.get('matched_name') or '').lower() or (i.get('e_number') or '').lower().replace(' ', '') == d for d in SOUTHAMPTON_DYES)
    ]
    if dyes:
        has_moderate_concern = True
        watch_items.append({
            'category': 'Artificial Colors',
            'severity': 'warning',
            'text': f"Contains synthetic food dyes ({', '.join(dyes)}) linked to attention and hyperactivity considerations in sensitive children."
        })

    # 6. High sugar / primary sweeteners
    sugar_names = {'sugar', 'sucrose', 'glucose syrup', 'corn syrup', 'high fructose corn syrup', 'dextrose', 'maltodextrin', 'fructose', 'invert sugar'}
    primary_sugars = []
    other_sugars = []
    for idx, i in enumerate(detected_list):
        nm = (i.get('matched_name') or i.get('raw_token') or '').lower()
        if any(s in nm for s in sugar_names):
            if idx < 3:
                primary_sugars.append(i.get('matched_name', nm))
            else:
                other_sugars.append(i.get('matched_name', nm))

    if primary_sugars:
        has_moderate_concern = True
        watch_items.append({
            'category': 'Added Sugars',
            'severity': 'warning',
            'text': f"Added sweeteners ({', '.join(primary_sugars)}) appear among the top 3 ingredients, indicating high sugar content."
        })
    elif other_sugars:
        watch_items.append({
            'category': 'Added Sugars',
            'severity': 'info',
            'text': f"Contains added sugars ({', '.join(other_sugars[:3])}). Check nutrition table for exact grams."
        })

    # 7. Intense sweeteners
    sweeteners = [
        i.get('matched_name') for i in detected_list
        if any(s in (i.get('matched_name') or '').lower() or (i.get('e_number') or '').lower().replace(' ', '') == s for s in INTENSE_SWEETENERS)
        or i.get('category') == 'Artificial Sweetener'
    ]
    if sweeteners:
        has_moderate_concern = True
        watch_items.append({
            'category': 'Artificial Sweeteners',
            'severity': 'warning',
            'text': f"Contains intense low-calorie sweeteners ({', '.join(sweeteners)}). Pediatric and health authorities advise limiting regular intake."
        })

    # 8. Curing salts
    salts = [
        i.get('matched_name') for i in detected_list
        if any(cs in (i.get('matched_name') or '').lower() or (i.get('e_number') or '').lower().replace(' ', '') == cs for cs in CURING_SALTS)
    ]
    if salts:
        has_moderate_concern = True
        watch_items.append({
            'category': 'Curing Salts / Nitrites',
            'severity': 'warning',
            'text': f"Contains curing salts ({', '.join(salts)}) commonly found in processed meats. Health authorities recommend limiting intake."
        })

    # 9. Unverified ingredients
    if unrecognized_count > 0:
        watch_items.append({
            'category': 'Unverified Ingredients',
            'severity': 'secondary',
            'text': f"{unrecognized_count} ingredient(s) could not be matched to our verified database. Unverified substances cannot be assumed safe."
        })

    # Determine status & badge
    if not detected_list or (unrecognized_count / max(len(detected_list), 1) >= 0.5 and not has_high_concern and not has_moderate_concern):
        status = 'Not enough information'
        badge_class = 'secondary'
        summary = 'There is not enough clear ingredient data to provide a complete watch-out assessment.'
    elif has_high_concern:
        status = 'Potential concern'
        badge_class = 'danger'
        summary = 'Important concerns identified: please check personal conflicts, allergens, or flagged additives before consuming.'
    elif has_moderate_concern:
        status = 'Use caution'
        badge_class = 'warning'
        summary = 'Pay attention to declared allergens, added sugars, artificial sweeteners, or sensitive additives listed below.'
    else:
        status = 'No specific concern identified'
        badge_class = 'success'
        summary = 'No specific high-priority concerns identified from the available ingredient list. Check the physical label if you have specific dietary restrictions, allergies, or health conditions.'

    return {
        'title': 'What Should I Watch Out For?',
        'status': status,
        'simple_status': status,
        'badge_class': badge_class,
        'summary': summary,
        'watch_list': watch_items,
        'items': watch_items,
        'no_concern_note': 'No specific high-priority concerns identified from the available ingredient list. Check the physical label if you have specific dietary restrictions or personal sensitivities.'
    }


def build_what_this_means_for_me(detected_list, flagged_allergens=None, personal_conflicts=None, child_suitability=None, regular_consumption=None, watch_outs=None, sections=None):
    """
    Build practical everyday takeaways answering:
    - What are the main things I should watch out for?
    - How often can I or my family consume or use this product?
    - Are there any declared allergens or substances I should avoid based on my preferences?
    - What information is missing that would help me make a better decision?
    - What alternative products or choices might be better?
    """
    flagged_allergens = flagged_allergens or []
    personal_conflicts = personal_conflicts or []
    sections = sections or {}
    child_suitability = child_suitability or {}
    regular_consumption = regular_consumption or {}
    watch_outs = watch_outs or {}

    is_cosmetic = child_suitability.get('is_cosmetic', False)

    # 1. Main takeaways
    takeaways = []
    if is_cosmetic:
        takeaways.append("This is an external cosmetic/personal care product. It is strictly formulated for topical skin or hair use and must not be consumed.")
        takeaways.append("Check skin sensitivities and follow package directions for application.")
    elif personal_conflicts:
        takeaways.append(f"Direct conflict with your profile: this product contains ingredients matching your dietary or allergy restrictions.")
    elif watch_outs.get('status') == 'Potential concern':
        takeaways.append("Review ingredients carefully: product contains substances flagged for health, pediatric, or allergy concerns.")
    elif watch_outs.get('status') == 'Use caution':
        takeaways.append("Suitable for occasional consumption, but keep an eye on added sweeteners, food dyes, or allergens.")
    else:
        takeaways.append("Based on the visible ingredients, this product consists of standard dietary ingredients with no high-risk alerts.")

    # 2. Consumption frequency guidance
    if is_cosmetic:
        frequency_advice = "External topical use only. Follow the manufacturer's directions on the bottle or tube."
    elif regular_consumption.get('simple_status') == 'Better to limit' or regular_consumption.get('status') == 'Limit frequency':
        frequency_advice = "Best enjoyed occasionally as a treat rather than as an everyday staple."
    elif regular_consumption.get('simple_status') == 'Generally reasonable based on available information' or 'Generally reasonable' in regular_consumption.get('status', ''):
        frequency_advice = "Appropriate for regular inclusion as part of a varied, balanced diet."
    else:
        frequency_advice = "Review package serving sizes and nutrition facts to determine suitable frequency."

    # 3. Allergen and dietary advice
    if personal_conflicts:
        allergen_advice = f"Action required: Avoid this product or consult your physician. Found: {', '.join(c['ingredient'] for c in personal_conflicts)}."
    elif flagged_allergens:
        allergen_advice = f"Contains recognized allergens ({', '.join(flagged_allergens)}). Keep away from individuals with diagnosed sensitivities."
    elif sections.get('may_contain'):
        allergen_advice = f"Notice: Made in a facility with possible cross-contamination ({sections['may_contain']})."
    else:
        allergen_advice = "No common major food allergens were detected in this ingredient list."

    # 4. Missing information note
    missing_info_note = "Quantitative nutrition values (exact grams of sugar, saturated fat, sodium, and calories per serving) were not extracted from the label. The full Nutrition Facts panel on the physical packaging is needed for exact portion calculations."

    # 5. Smart shopping tips & better alternatives
    shopping_tips = []
    if is_cosmetic:
        shopping_tips.append("For sensitive skin, look for fragrance-free and hypoallergenic formulas.")
        shopping_tips.append("Always perform a small patch test on your forearm before using a new cosmetic product.")
    else:
        if regular_consumption.get('status') == 'Limit frequency':
            shopping_tips.append("Look for alternative brands with shorter ingredient lists and no artificial colors or intense sweeteners.")
            shopping_tips.append("Choose whole-food snack alternatives such as fresh fruit, plain roasted nuts, or minimally processed whole grains.")
            shopping_tips.append("Compare nutrition labels on similar products to pick options with lower added sugar and sodium.")
        else:
            shopping_tips.append("Look for products with simple, recognizable whole-food ingredients.")
            shopping_tips.append("Pair this item with fresh produce and plenty of water for a balanced plate.")
            shopping_tips.append("Check the expiration or best-before date on the physical package.")

    return {
        'main_takeaways': takeaways,
        'frequency_advice': frequency_advice,
        'allergen_advice': allergen_advice,
        'missing_info_note': missing_info_note,
        'shopping_tips': shopping_tips
    }

# Max deduction is capped at 100 (score floor = 0)
# Score formula: 100 - sum(per-ingredient penalty) capped at [0, 100]
# Penalty per ingredient = SAFETY_SCORE_WEIGHTS[safety_level]
# Verdict thresholds:
#   >= 85  → "Clean & Safe"
#   >= 60  → "Moderate Caution"
#    < 60  → "High Risk"


OCR_CORRECTIONS = {
    'peanul': 'peanut',
    'peanuls': 'peanut',
    'peanuts': 'peanut',
    'groundnul': 'groundnut',
    'groundnuls': 'groundnut',
    'tumeric': 'turmeric',
    'turmaric': 'turmeric',
    'palmolien': 'palmolein',
    'palmolin': 'palmolein',
    'potatos': 'potato',
    'potao': 'potato',
    'potaotes': 'potato',
    'chillies': 'chilli',
    'chili': 'chilli',
    'skimed': 'skimmed',
    'lecitin': 'lecithin',
    'maltodextren': 'maltodextrin',
    'xantham': 'xanthan',
    'xanthangum': 'xanthan gum',
    'sunfloweroil': 'sunflower oil',
    'coconutoil': 'coconut oil',
    'carroway': 'caraway',
    'corriander': 'coriander',
    'coriandar': 'coriander',
    'cardamon': 'cardamom',
    'asafetida': 'asafoetida',
    'asafoetida': 'asafoetida',
    'haldii': 'haldi',
    'dhaania': 'dhania',
    'jeeraa': 'jeera',
}

COMMON_FOOD_QUALIFIERS = {
    'extract', 'powder', 'oil', 'flour', 'seed', 'seeds', 'leaf', 'leaves',
    'crushed', 'roasted', 'organic', 'pure', 'natural', 'dried', 'liquid',
    'flakes', 'syrup', 'concentrate', 'paste', 'ground', 'refined', 'raw',
    'whole', 'split', 'meal', 'root', 'roots', 'juice', 'puree'
}


def get_substantive_root(text):
    """Strip common culinary qualifiers/modifiers to isolate the base food noun for robust fuzzy comparison."""
    if not text:
        return ""
    words = [w for w in re.sub(r'[^\w\s]', '', text.lower()).split() if w not in COMMON_FOOD_QUALIFIERS]
    return ' '.join(words) if words else text.lower().strip()


def normalize_inverted_phrase(text):
    """Normalize inverted label phrases like 'Flour (Wheat)' -> 'Wheat flour' or 'Oil (Palmolein)' -> 'Palmolein oil'."""
    if not text:
        return ""
    m = re.match(r'^([a-zA-Z\s]+)\s*\(\s*([a-zA-Z\s]+)\s*\)$', text.strip())
    if m:
        head, inside = m.group(1).strip(), m.group(2).strip()
        if not re.match(r'^[eE]\s*\d+|^\d+%', inside):
            return f"{inside} {head}".strip()
    return text


def extract_percentage(token):
    """Extract percentage like (60%) or 12% from an ingredient string and return (clean_text, percentage_str)."""
    if not token:
        return "", None
    m = re.search(r'\(?\s*(\d+(?:\.\d+)?\s*%)\s*\)?', token)
    if m:
        pct = m.group(1).replace(' ', '')
        clean = re.sub(r'\(?\s*\d+(?:\.\d+)?\s*%\s*\)?', '', token).strip()
        return clean, pct
    return token, None


def is_ocr_artifact(token):
    """Check if token is nonsensical OCR garbage or broken characters."""
    t = token.strip()
    if len(t) <= 1:
        return True
    # If it is an E-number or INS code (e.g. E621, INS 330), it is valid
    if re.search(r'\b(?:ins|e)[-\s]*\d{3,4}[a-zA-Z]?\b', t, re.IGNORECASE):
        return False
    if t.isdigit() or re.match(r'^\d+%$', t):
        return False
    alpha = sum(c.isalpha() for c in t)
    total = len(t)
    if total > 0 and (alpha / total) < 0.4:
        return True
    if re.search(r'[^a-zA-Z0-9\s]{3,}', t):
        return True
    words = [w for w in re.split(r'\s+', t) if w.isalpha()]
    for w in words:
        if len(w) >= 4 and not any(v in w.lower() for v in 'aeiouy'):
            return True
    if re.match(r'^(x#|#|\$|@|\*|&|_)', t):
        return True
    return False


def split_ingredient_tokens(text):
    """
    Splits text on top-level delimiters (commas, semicolons, bullets, newlines)
    while respecting nested parentheses so compound ingredients like:
    'Potato flakes (Potato (60%), Salt), Palmolein Oil'
    are kept intact for hierarchical parsing.
    """
    items = []
    current = []
    depth = 0
    for char in text:
        if char in '([{':
            depth += 1
            current.append(char)
        elif char in ')]}':
            depth = max(0, depth - 1)
            current.append(char)
        elif char in ',;•\n\r' and depth == 0:
            token = "".join(current).strip()
            if token:
                items.append(token)
            current = []
        else:
            current.append(char)
    if current:
        token = "".join(current).strip()
        if token:
            items.append(token)
    return items


def filter_label_noise(tokens):
    """Filters out headers, product titles, serving instructions, and marketing slogans."""
    clean_list = []
    noise_patterns = [
        r'^(batch\s*no|lot\s*no|mfg\s*date|exp\s*date|use\s*by|best\s*before)',
        r'^(net\s*wt|net\s*quantity|gross\s*wt|mrp|rs\.?|lic\s*no|fssai)',
        r'^(serving\s*size|servings\s*per|store\s*in\s*a\s*cool|keep\s*refrigerated)',
        r'^(manufactured\s*by|marketed\s*by|packed\s*by|customer\s*care)',
    ]
    for t in tokens:
        t_clean = t.strip()
        if not t_clean or len(t_clean) < 2:
            continue
        if any(re.search(p, t_clean, re.IGNORECASE) for p in noise_patterns):
            continue
        clean_list.append(t_clean)
    return clean_list


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

        # 2. Fallback: load from data/ingredients.csv and data/food_ingredients.csv
        return self._load_csv_catalog()

    def refresh_catalog(self):
        """Force-reload the catalog (call after seeding DB)."""
        self._catalog = None

    def _model_to_dict(self, ingredient):
        """Convert an Ingredient ORM model instance to the dict format used internally."""
        safety = ingredient.safety_level or ingredient.safety_rating or 'Safe'
        return {
            'name': ingredient.name,
            'aliases': ingredient.aliases or '',
            'e_number': ingredient.e_number,
            'category': ingredient.category or 'General',
            'safety_rating': safety,
            'safety_level': safety,
            'allergen_type': ingredient.allergen_type,
            'allergen_tag': ingredient.allergen_tag or '',
            'diet_flags': ingredient.diet_flags or '',
            'description': ingredient.description,
            'health_effects': ingredient.health_effects,
            'banned_status': ingredient.banned_status,
            'ingredient_type': getattr(ingredient, 'ingredient_type', 'food'),
            'what_is_it': getattr(ingredient, 'what_is_it', None),
            'why_used': getattr(ingredient, 'why_used', None),
            'common_uses': getattr(ingredient, 'common_uses', None),
            'child_considerations': getattr(ingredient, 'child_considerations', None),
            'regular_consumption': getattr(ingredient, 'regular_consumption', None),
            'source_attribution': getattr(ingredient, 'source_attribution', 'FSSAI / Codex Alimentarius / ICMR-NIN'),
            'is_approved': getattr(ingredient, 'is_approved', True),
        }

    def _load_csv_catalog(self):
        """Load catalog from data/ingredients.csv and data/food_ingredients.csv (fallback path)."""
        import csv
        base_dir = Path(__file__).resolve().parent.parent.parent / 'data'
        csv_path = base_dir / 'ingredients.csv'
        food_csv_path = base_dir / 'food_ingredients.csv'

        catalog = []
        seen_names = set()

        # 1. Base ingredients (80 records)
        if csv_path.exists():
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row['name'].strip()
                        safety = row.get('safety_level', 'Safe')
                        catalog.append({
                            'name': name,
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
                            'ingredient_type': 'additive' if row.get('e_number') else 'food',
                            'what_is_it': None,
                            'why_used': None,
                            'common_uses': None,
                            'child_considerations': None,
                            'regular_consumption': None,
                            'source_attribution': 'FSSAI / Codex Alimentarius',
                            'is_approved': True
                        })
                        seen_names.add(name.lower())
            except Exception:
                pass

        # 2. Food ingredients (194 records)
        if food_csv_path.exists():
            try:
                with open(food_csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row['name'].strip()
                        name_lower = name.lower()
                        safety = row.get('safety_level', 'Safe')
                        if name_lower in seen_names:
                            for item in catalog:
                                if item['name'].lower() == name_lower:
                                    if row.get('aliases'):
                                        item['aliases'] = f"{item['aliases']}, {row['aliases']}" if item['aliases'] else row['aliases']
                                    item['ingredient_type'] = row.get('ingredient_type', 'food')
                                    item['what_is_it'] = row.get('what_is_it')
                                    item['why_used'] = row.get('why_used')
                                    item['common_uses'] = row.get('common_uses')
                                    item['child_considerations'] = row.get('child_considerations')
                                    item['regular_consumption'] = row.get('regular_consumption')
                                    item['source_attribution'] = row.get('source_attribution', 'FSSAI / Codex Alimentarius / ICMR-NIN')
                                    break
                        else:
                            catalog.append({
                                'name': name,
                                'aliases': row.get('aliases', ''),
                                'e_number': row.get('e_number') or None,
                                'category': row.get('category', 'Food Ingredients'),
                                'safety_rating': safety,
                                'safety_level': safety,
                                'allergen_type': None,
                                'allergen_tag': row.get('allergen_tag', ''),
                                'diet_flags': row.get('diet_flags', ''),
                                'description': None,
                                'health_effects': row.get('health_effects'),
                                'banned_status': row.get('banned_status', 'False') == 'True',
                                'ingredient_type': row.get('ingredient_type', 'food'),
                                'what_is_it': row.get('what_is_it'),
                                'why_used': row.get('why_used'),
                                'common_uses': row.get('common_uses'),
                                'child_considerations': row.get('child_considerations'),
                                'regular_consumption': row.get('regular_consumption'),
                                'source_attribution': row.get('source_attribution', 'FSSAI / Codex Alimentarius / ICMR-NIN'),
                                'is_approved': True
                            })
                            seen_names.add(name_lower)
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
        - Split on top-level delimiters (commas, semicolons, bullets, newlines) while preserving nested parentheses.
        - Filter out product titles, date codes, packaging slogans, and noise.
        - For each chunk, extract the ingredient name separately from any trailing E-number parenthetical.
        - Discard pure digit tokens or single-character fragments.
        """
        if raw_text is None:
            return []

        cleaned = clean_text(raw_text)
        if not cleaned:
            return []

        # Split on list separators respecting parentheses
        raw_items = split_ingredient_tokens(cleaned)
        filtered_items = filter_label_noise(raw_items)

        tokens = []
        seen_lower = set()

        for item in filtered_items:
            item = item.strip()
            if not item:
                continue

            # Remove trailing parentheticals that are ONLY an E-number e.g. "(E211)"
            item_no_enum = re.sub(
                r'\s*\(\s*[eE]\s*\d{3,4}[a-zA-Z]?\s*\)',
                '',
                item,
            ).strip()

            # Clean outer brackets
            trimmed = re.sub(r'[\[\]\{\}\*]', '', item_no_enum).strip()
            trimmed = re.sub(r'\s+', ' ', trimmed)

            if not trimmed or len(trimmed) < 2 or trimmed.isdigit():
                continue

            key = trimmed.lower()
            if key in seen_lower:
                continue
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
                norm_e = item['e_number'].replace(' ', '').replace('-', '').upper()
                e_map[norm_e] = idx
                digits = re.sub(r'^[A-Z]+', '', norm_e)
                if digits:
                    e_map[digits] = idx

            for alias in re.split(r'[,;]+', item.get('aliases') or ''):
                alias_clean = alias.strip().lower()
                if alias_clean:
                    alias_map[alias_clean] = idx
                    ins_match = re.search(r'\bins\s*[-]?(\d{3,4}[a-zA-Z]?)\b', alias_clean)
                    if ins_match:
                        e_map[f"INS{ins_match.group(1)}"] = idx
                        e_map[f"E{ins_match.group(1)}"] = idx
                        e_map[ins_match.group(1)] = idx

        return names, alias_map, e_map

    def match_ingredient_detailed(self, token, score_cutoff=72):
        """
        Multi-Stage Automatic Recognition Engine:
        Returns (catalog_dict or None, confidence_score, recognition_status)
        where recognition_status is one of:
          - 'Recognized'
          - 'Recognized — needs review'
          - 'Unidentified'
          - 'OCR issue'
        """
        if not token or not str(token).strip():
            return None, 0.0, 'Unidentified'

        catalog = self.catalog
        if not catalog:
            return None, 0.0, 'Unidentified'

        names, alias_map, e_map = self._build_index()

        # Step 1: Clean and normalize inverted phrasing
        clean_tok, pct = extract_percentage(token)
        clean_tok = normalize_inverted_phrase(clean_tok)
        t_clean = re.sub(r'[\[\]\{\}\*\.]', '', clean_tok).strip()
        t_clean = re.sub(r'^[•\-\*\.]\s*', '', t_clean).strip()
        t_lower = t_clean.lower()

        # Check OCR garbage
        if is_ocr_artifact(t_lower):
            return None, 0.0, 'OCR issue'

        # Stage 1: Direct E-number / INS match (highest priority, confidence 100)
        e_hit = re.search(r'\b(?:ins|e)[-\s]*(\d{3,4}[a-zA-Z]?)\b', t_lower)
        if e_hit:
            norm_e = f"E{e_hit.group(1).upper()}"
            if norm_e in e_map:
                return catalog[e_map[norm_e]], 100.0, 'Recognized'
            if e_hit.group(1) in e_map:
                return catalog[e_map[e_hit.group(1)]], 100.0, 'Recognized'

        # Stage 2: Exact Canonical Name Match (case-insensitive)
        if t_lower in names:
            return catalog[names.index(t_lower)], 100.0, 'Recognized'

        # Stage 3: Normalized Name Match (singular/plural, whitespace, punctuation)
        t_norm = re.sub(r'[^\w\s]', '', t_lower)
        if t_norm in names:
            return catalog[names.index(t_norm)], 98.0, 'Recognized'
        if t_norm.endswith('s') and t_norm[:-1] in names:
            return catalog[names.index(t_norm[:-1])], 98.0, 'Recognized'
        if t_norm.endswith('es') and t_norm[:-2] in names:
            return catalog[names.index(t_norm[:-2])], 98.0, 'Recognized'

        # Stage 4: Synonym & Indian / Botanical Alias match
        if t_lower in alias_map:
            return catalog[alias_map[t_lower]], 95.0, 'Recognized'
        if t_norm in alias_map:
            return catalog[alias_map[t_norm]], 95.0, 'Recognized'
        if t_norm.endswith('s') and t_norm[:-1] in alias_map:
            return catalog[alias_map[t_norm[:-1]]], 94.0, 'Recognized'
        if t_norm.endswith('es') and t_norm[:-2] in alias_map:
            return catalog[alias_map[t_norm[:-2]]], 94.0, 'Recognized'

        # Stage 5: Conservative OCR Typo Correction
        if t_lower in OCR_CORRECTIONS:
            corr = OCR_CORRECTIONS[t_lower]
            if corr in names:
                return catalog[names.index(corr)], 92.0, 'Recognized'
            if corr in alias_map:
                return catalog[alias_map[corr]], 90.0, 'Recognized'

        # Stage 5b: Substantive Root Match (e.g. "Whole Peanuts" -> "Peanut", "Roasted Cashews" -> "Cashew")
        root_input = get_substantive_root(t_clean)
        if root_input and root_input != t_lower:
            root_norm = re.sub(r'[^\w\s]', '', root_input)
            if root_input in names:
                return catalog[names.index(root_input)], 96.0, 'Recognized'
            if root_norm in names:
                return catalog[names.index(root_norm)], 96.0, 'Recognized'
            if root_norm.endswith('s') and root_norm[:-1] in names:
                return catalog[names.index(root_norm[:-1])], 96.0, 'Recognized'
            if root_input in alias_map:
                return catalog[alias_map[root_input]], 95.0, 'Recognized'
            if root_norm in alias_map:
                return catalog[alias_map[root_norm]], 95.0, 'Recognized'
            if root_norm.endswith('s') and root_norm[:-1] in alias_map:
                return catalog[alias_map[root_norm[:-1]]], 94.0, 'Recognized'

        # Stage 6: Word-order Invariant Match (e.g. "palmolein oil" vs "palm olein oil")
        t_words = set(t_norm.split())
        if len(t_words) > 1:
            for idx, item in enumerate(catalog):
                n_words = set(re.sub(r'[^\w\s]', '', item['name'].lower()).split())
                if t_words == n_words or (len(n_words) > 1 and n_words.issubset(t_words)):
                    return catalog[idx], 90.0, 'Recognized'

        # Stage 7: RapidFuzz Matching with substantive root verification to prevent false matches
        if RAPIDFUZZ_AVAILABLE:
            root_input = get_substantive_root(t_lower)
            candidates = process.extract(
                t_lower,
                names,
                scorer=fuzz.token_sort_ratio,
                limit=5,
                score_cutoff=score_cutoff,
            )
            for matched_name, score, idx in candidates:
                root_match = get_substantive_root(matched_name)
                if fuzz.token_sort_ratio(root_input, root_match) >= 65:
                    status = 'Recognized' if score >= 85 else 'Recognized — needs review'
                    return catalog[idx], round(score, 1), status

            alias_keys = list(alias_map.keys())
            if alias_keys:
                alias_candidates = process.extract(
                    t_lower,
                    alias_keys,
                    scorer=fuzz.token_sort_ratio,
                    limit=5,
                    score_cutoff=score_cutoff,
                )
                for matched_alias, score, _ in alias_candidates:
                    root_match = get_substantive_root(matched_alias)
                    if fuzz.token_sort_ratio(root_input, root_match) >= 65:
                        idx = alias_map[matched_alias]
                        status = 'Recognized' if score >= 85 else 'Recognized — needs review'
                        return catalog[idx], round(score, 1), status
        else:
            # Substring fallback
            for item in catalog:
                if item['name'].lower() in t_lower or t_lower in item['name'].lower():
                    return item, 85.0, 'Recognized'
            for alias_key, idx in alias_map.items():
                if alias_key in t_lower or t_lower in alias_key:
                    return catalog[idx], 80.0, 'Recognized — needs review'

        # Stage 8: Genuinely unindexed / unidentified
        return None, 0.0, 'Unidentified'

    def match_ingredient(self, token, score_cutoff=72):
        """Return (catalog_dict, confidence_score) for backward compatibility with 2-tuple callers."""
        item, score, status = self.match_ingredient_detailed(token, score_cutoff=score_cutoff)
        return item, score

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
            clean_tok, pct = extract_percentage(token)
            clean_tok = normalize_inverted_phrase(clean_tok)
            matched_item, score, status = self.match_ingredient_detailed(clean_tok)

            if matched_item:
                safety = matched_item.get('safety_rating') or matched_item.get('safety_level') or 'Safe'
                allergen_tag = matched_item.get('allergen_tag') or ''
                diet_flags = matched_item.get('diet_flags') or ''
                details = build_ingredient_assessment(
                    matched_item,
                    token,
                    is_matched=True,
                    recognition_status=status,
                    percentage=pct
                )

                info = {
                    'raw_token': token,
                    'clean_token': clean_tok,
                    'matched_name': matched_item['name'],
                    'display_name': details.get('display_name', matched_item['name']),
                    'percentage': pct,
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
                    'ingredient_type': matched_item.get('ingredient_type', 'food'),
                    'recognition_status': status,
                    'purpose': details['purpose'],
                    'what_it_does': details.get('what_it_does', details['purpose']),
                    'plain_explanation': details['plain_explanation'],
                    'simple_explanation': details.get('simple_explanation', details['plain_explanation']),
                    'common_uses': details.get('common_uses', 'Common food preparation.'),
                    'known_safety_concerns': details['known_safety_concerns'],
                    'age_considerations': details['age_considerations'],
                    'child_assessment': details['child_assessment'],
                    'child_concerns': details.get('child_concerns', details['known_safety_concerns']),
                    'regular_consumption_note': details.get('regular_consumption_note', 'Standard food ingredient.'),
                    'simple_status': details.get('simple_status', 'No specific concern identified'),
                    'simple_badge': details.get('simple_badge', 'success'),
                    'allergen_info': details['allergen_info'],
                    'sources': details['sources'],
                    'is_unrecognized': False,
                    'short_description': details.get('short_description', ''),
                    'safety_status': details.get('safety_status', 'No specific concern identified'),
                    'safety_status_badge': details.get('safety_status_badge', 'success'),
                    'safety_short_explanation': details.get('safety_short_explanation', ''),
                    'children_suitability_status': details.get('children_suitability_status', 'Generally suitable for children when used in ordinary food quantities'),
                    'children_suitability_badge': details.get('children_suitability_badge', 'success'),
                    'children_guidance': details.get('children_guidance', ''),
                    'age_guidance_text': details.get('age_guidance_text', 'No specific minimum age established from the available information.'),
                    'age_brackets': details.get('age_brackets', []),
                    'choking_hazard': details.get('choking_hazard', False),
                    'choking_hazard_note': details.get('choking_hazard_note', ''),
                    'allergen_warning': details.get('allergen_warning', ''),
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
                item_tags = [t.strip().lower() for t in allergen_tag.split(',') if t.strip()]
                user_allergy_roots = [a.rstrip('s').lower() for a in user_allergies_normalized]
                for tag in item_tags:
                    tag_root = tag.rstrip('s').lower()
                    if tag in user_allergies_normalized or tag_root in user_allergy_roots or any(tag_root == a or a == tag_root for a in user_allergy_roots):
                        conflict_msg = f"{matched_item['name']}: matches your selected {tag} allergy."
                        if conflict_msg not in [c['message'] for c in personal_conflicts]:
                            personal_conflicts.append({
                                'ingredient': matched_item['name'],
                                'type': 'allergy',
                                'tag': tag,
                                'message': conflict_msg
                            })

                for allergen_label, keywords in self.COMMON_ALLERGENS.items():
                    label_root = allergen_label.lower().rstrip('s')
                    if label_root in user_allergy_roots or allergen_label.lower() in user_allergies_normalized:
                        if any(kw in token.lower() or kw in matched_item['name'].lower() for kw in keywords):
                            conflict_msg = f"{matched_item['name']}: matches your selected {allergen_label} allergy."
                            if conflict_msg not in [c['message'] for c in personal_conflicts]:
                                personal_conflicts.append({
                                    'ingredient': matched_item['name'],
                                    'type': 'allergy',
                                    'tag': allergen_label.lower(),
                                    'message': conflict_msg
                                })

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

                details = build_ingredient_assessment(
                    None,
                    token,
                    is_matched=False,
                    recognition_status=status,
                    percentage=pct
                )
                detected_list.append({
                    'raw_token': token,
                    'clean_token': clean_tok,
                    'matched_name': token,
                    'display_name': token,
                    'percentage': pct,
                    'e_number': None,
                    'category': 'Uncategorized',
                    'safety_rating': 'Unknown',
                    'safety_level': 'Unknown',
                    'allergen_type': None,
                    'allergen_tag': '',
                    'diet_flags': '',
                    'description': details['simple_explanation'],
                    'health_effects': 'Unverified substance.',
                    'confidence': 0.0,
                    'banned_status': False,
                    'ingredient_type': 'unverified',
                    'recognition_status': status,
                    'purpose': details['purpose'],
                    'what_it_does': details['what_it_does'],
                    'plain_explanation': details['plain_explanation'],
                    'simple_explanation': details['simple_explanation'],
                    'common_uses': details.get('common_uses', 'N/A'),
                    'known_safety_concerns': details['known_safety_concerns'],
                    'age_considerations': details['age_considerations'],
                    'child_assessment': details['child_assessment'],
                    'child_concerns': details['child_concerns'],
                    'regular_consumption_note': details['regular_consumption_note'],
                    'simple_status': details['simple_status'],
                    'simple_badge': details['simple_badge'],
                    'allergen_info': details['allergen_info'],
                    'sources': details['sources'],
                    'is_unrecognized': True,
                    'short_description': details.get('short_description', ''),
                    'safety_status': details.get('safety_status', 'Insufficient information'),
                    'safety_status_badge': details.get('safety_status_badge', 'secondary'),
                    'safety_short_explanation': details.get('safety_short_explanation', ''),
                    'children_suitability_status': details.get('children_suitability_status', 'Insufficient information to provide age-specific guidance'),
                    'children_suitability_badge': details.get('children_suitability_badge', 'secondary'),
                    'children_guidance': details.get('children_guidance', ''),
                    'age_guidance_text': details.get('age_guidance_text', 'No specific minimum age established from the available information.'),
                    'age_brackets': details.get('age_brackets', []),
                    'choking_hazard': details.get('choking_hazard', False),
                    'choking_hazard_note': details.get('choking_hazard_note', ''),
                    'allergen_warning': details.get('allergen_warning', ''),
                })

        # Database Expansion Logging: record unverified or review-needed tokens
        try:
            from flask import current_app
            if current_app:
                from app.models.ingredient import UnidentifiedIngredient
                from app import db
                from datetime import datetime, timezone
                for ing in detected_list:
                    rec_status = ing.get('recognition_status')
                    if rec_status in ('Unidentified', 'Recognized — needs review', 'OCR issue'):
                        raw = ing.get('raw_token') or ''
                        clean = (ing.get('clean_token') or raw).strip()
                        if clean and len(clean) >= 2 and not clean.isdigit():
                            existing_rec = UnidentifiedIngredient.query.filter_by(clean_token=clean).first()
                            if existing_rec:
                                existing_rec.occurrence_count += 1
                                existing_rec.last_seen = datetime.now(timezone.utc)
                                if ing.get('confidence'):
                                    existing_rec.confidence = int(ing.get('confidence'))
                            else:
                                new_rec = UnidentifiedIngredient(
                                    raw_token=raw[:250],
                                    clean_token=clean[:250],
                                    confidence=int(ing.get('confidence', 0)),
                                    suggested_match=(ing.get('matched_name') or '')[:140],
                                    status='pending',
                                    occurrence_count=1,
                                    first_seen=datetime.now(timezone.utc),
                                    last_seen=datetime.now(timezone.utc)
                                )
                                db.session.add(new_rec)
                db.session.commit()
        except Exception:
            pass

        # Compute score and verdict
        safety_score = self.compute_score(detected_list)
        base_verdict, base_badge = self.score_to_verdict(safety_score)

        # Personal conflict override
        has_conflict = len(personal_conflicts) > 0
        if has_conflict:
            displayed_verdict = 'Avoid'
            displayed_badge = 'danger'
        else:
            displayed_verdict = base_verdict
            displayed_badge = base_badge

        # Evaluate child suitability, regular consumption, and label sections
        child_suitability = evaluate_child_suitability(detected_list, raw_text)
        regular_consumption = evaluate_regular_consumption(detected_list, raw_text)

        from app.services.ocr_service import OCRService
        sections = OCRService.detect_sections(raw_text)

        unrecognized_count = sum(1 for i in detected_list if i.get('is_unrecognized'))

        watch_outs = evaluate_watch_outs(
            detected_list=detected_list,
            flagged_allergens=sorted(flagged_allergens),
            personal_conflicts=personal_conflicts,
            sections=sections,
            unrecognized_count=unrecognized_count
        )

        what_this_means_for_me = build_what_this_means_for_me(
            detected_list=detected_list,
            flagged_allergens=sorted(flagged_allergens),
            personal_conflicts=personal_conflicts,
            child_suitability=child_suitability,
            regular_consumption=regular_consumption,
            watch_outs=watch_outs,
            sections=sections
        )

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
            'child_suitability': child_suitability,
            'regular_consumption': regular_consumption,
            'watch_outs': watch_outs,
            'what_this_means_for_me': what_this_means_for_me,
            'sections': sections,
            'unrecognized_count': unrecognized_count,
            'stats': {
                'total_detected': len(detected_list),
                'caution_count': caution_count,
                'avoid_count': avoid_count,
                'harmful_count': harmful_count,
                'allergen_count': len(flagged_allergens),
                'unrecognized_count': unrecognized_count,
                'recognized_count': sum(1 for i in detected_list if i.get('recognition_status') == 'Recognized'),
                'review_count': sum(1 for i in detected_list if i.get('recognition_status') == 'Recognized — needs review'),
                'ocr_issue_count': sum(1 for i in detected_list if i.get('recognition_status') == 'OCR issue'),
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
