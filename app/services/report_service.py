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
        summary = analysis_result.get('summary', 'Safe & Clean')
        color_map = {
            'Safe & Clean': colors.HexColor('#22c55e'),
            'Moderate Caution': colors.HexColor('#eab308'),
            'High Risk': colors.HexColor('#ef4444')
        }
        status_color = color_map.get(summary, colors.HexColor('#3b82f6'))

        summary_table_data = [
            [Paragraph("<b>Safety Assessment:</b>", styles['Normal']), Paragraph(f"<b><font color='{status_color.hexval()}'>{summary.upper()}</font></b>", styles['Normal'])],
            [Paragraph("<b>Allergens Detected:</b>", styles['Normal']), Paragraph(", ".join(analysis_result.get('flagged_allergens', [])) or "None Detected", styles['Normal'])],
            [Paragraph("<b>Total Ingredients Identified:</b>", styles['Normal']), str(len(analysis_result.get('detected_ingredients', [])))]
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
                ing.get('category', 'Additive'),
                ing.get('safety_rating', 'Safe'),
                ing.get('allergen_type') or "None"
            ])

        ing_table = Table(table_rows, colWidths=[150, 70, 110, 80, 120])
        ing_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#166534')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ffffff')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(ing_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer
