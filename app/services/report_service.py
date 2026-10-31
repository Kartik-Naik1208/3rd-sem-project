import io
from datetime import datetime

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class ReportGenerator:
    """Generates PDF safety assessment reports using ReportLab."""

    @staticmethod
    def generate_pdf(product_name, analysis_result, user_name="Guest"):
        """Compiles analysis into an in-memory PDF buffer."""
        buffer = io.BytesIO()

        if not REPORTLAB_AVAILABLE:
            # Fallback if ReportLab is not installed yet
            buffer.write(b"%PDF-1.4 Fallback minimal PDF. ReportLab package pending installation.")
            buffer.seek(0)
            return buffer

        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40, leftMargin=40,
            topMargin=40, bottomMargin=40
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#166534'),
            spaceAfter=8
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#64748b'),
            spaceAfter=14
        )
        section_style = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#1e293b'),
            spaceBefore=12,
            spaceAfter=6
        )

        elements = []

        # Header
        elements.append(Paragraph("IngredientIQ Safety & Allergen Report", title_style))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        elements.append(Paragraph(f"Product: <b>{product_name}</b> | Evaluated: {now_str} | User: {user_name}", subtitle_style))
        elements.append(Spacer(1, 10))

        # Overall Status Card
        summary = analysis_result.get('summary', 'Clean & Safe')
        color_map = {
            'Clean & Safe': colors.HexColor('#16a34a'),
            'Safe & Clean': colors.HexColor('#16a34a'),
            'Moderate Caution': colors.HexColor('#d97706'),
            'High Risk': colors.HexColor('#dc2626'),
            'Avoid': colors.HexColor('#dc2626')
        }
        status_color = color_map.get(summary, colors.HexColor('#2563eb'))

        child_stat = analysis_result.get('child_suitability', {}).get('status', 'No specific concern identified')
        regular_stat = analysis_result.get('regular_consumption', {}).get('status', 'Generally reasonable based on available data')

        summary_table_data = [
            [Paragraph("<b>Overall Verdict:</b>", styles['Normal']), Paragraph(f"<b><font color='{status_color.hexval()}'>{summary.upper()}</font></b>", styles['Normal'])],
            [Paragraph("<b>Child Suitability:</b>", styles['Normal']), Paragraph(f"<b>{child_stat}</b>", styles['Normal'])],
            [Paragraph("<b>Regular Consumption:</b>", styles['Normal']), Paragraph(f"<b>{regular_stat}</b>", styles['Normal'])],
            [Paragraph("<b>Allergens Detected:</b>", styles['Normal']), Paragraph(", ".join(analysis_result.get('flagged_allergens', [])) or "None Detected", styles['Normal'])],
            [Paragraph("<b>Total Ingredients:</b>", styles['Normal']), str(len(analysis_result.get('detected_ingredients', [])))]
        ]
        summary_table = Table(summary_table_data, colWidths=[160, 370])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 15))

        # Ingredients Table
        elements.append(Paragraph("Identified Ingredients Breakdown", section_style))
        table_rows = [["Ingredient", "E-Number", "Category", "Rating", "Allergen"]]

        for ing in analysis_result.get('detected_ingredients', []):
            table_rows.append([
                ing.get('matched_name', ing.get('raw_token', '-')),
                ing.get('e_number') or "-",
                ing.get('category', 'General'),
                ing.get('safety_level') or ing.get('safety_rating', 'Safe'),
                ing.get('allergen_type') or ing.get('allergen_tag') or "None"
            ])

        ing_table = Table(table_rows, colWidths=[160, 70, 110, 80, 110])
        ing_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ffffff')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('PADDING', (0, 1), (-1, -1), 5),
        ]))
        elements.append(ing_table)
        elements.append(Spacer(1, 15))

        # Medical Disclaimer
        disclaimer_style = ParagraphStyle(
            'Disclaimer',
            parent=styles['Normal'],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#64748b'),
            spaceBefore=10
        )
        elements.append(Paragraph("<b>Disclaimer:</b> IngredientIQ provides automated nutritional transparency and educational guidance compiled from public scientific sources (EFSA, FDA, WHO, AAP). It does not constitute professional medical, pediatric, or clinical allergy advice.", disclaimer_style))

        doc.build(elements)
        buffer.seek(0)
        return buffer
