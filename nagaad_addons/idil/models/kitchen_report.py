from odoo import models, fields, api
import xlsxwriter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import base64
from datetime import datetime


class Kitchen_ReportWizard(models.TransientModel):
    _name = 'idil.kitchen.report'
    _description = 'Kitchen Report Wizard'

    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def generate_pdf_report(self):

        company = self.env.company  # Fetch the active company
        company_logo = company.logo if company.logo else None
        company_name = company.name or "Your Company"
        company_address = f"{company.partner_id.city or ''}, {company.partner_id.country_id.name or ''}"
        company_phone = company.partner_id.phone or "N/A"
        company_email = company.partner_id.email or "N/A"
        company_website = company.website or "N/A"

        # Create PDF document
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=30,
            leftMargin=30,
            topMargin=40,
            bottomMargin=30,
        )
        elements = []

        # Styles
        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            name='Header',
            parent=styles['Title'],
            fontSize=18,
            textColor=colors.HexColor("#B6862D"),  # Golden color
            alignment=1  # Center aligned
        )
        subtitle_style = ParagraphStyle(
            name='Subtitle',
            parent=styles['Normal'],
            fontSize=12,
            alignment=1  # Center aligned
        )
        left_align_style = ParagraphStyle(
            name='LeftAlign',
            parent=styles['Normal'],
            fontSize=12,
            alignment=0  # Left aligned
        )
        partner_align_style = ParagraphStyle(
            name='LeftAlign',
            parent=styles['Normal'],
            fontSize=12,
            alignment=0,  # Left-aligned
            spaceAfter=6,  # Space after paragraph

        )

        # Add company logo
        if company_logo:
            # Convert the company logo (binary) to an image
            logo_image = Image(io.BytesIO(base64.b64decode(company_logo)), width=120, height=60)
            elements.append(logo_image)
        else:
            # Placeholder for no logo
            elements.append(Paragraph("<b>No Logo Available</b>", header_style))

        elements.append(Spacer(1, 12))

        # Add company name and details
        company_name_paragraph = Paragraph(f"<b>{company_name.upper()}</b>", header_style)
        company_details_paragraph = Paragraph(
            f"{company_address}<br/>"
            f"Phone No.: {company_phone}<br/>"
            f"Email: {company_email}<br/>"
            f"Web: {company_website}",
            subtitle_style
        )
        elements.extend([company_name_paragraph, Spacer(1, 6), company_details_paragraph, Spacer(1, 20)])

        # Add Dates and Partner Information on the Left
        date_range = Paragraph(
            f"<b>Date from:</b> {self.start_date.strftime('%d/%m/%Y')}<br/>"
            f"<b>Date to:</b> {self.end_date.strftime('%d/%m/%Y')}<br/>",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))
        # Add Partner Information with Controlled Position

        # Table Header
        data = [["Kitchen Name", "Amount Transferred", "Amount Cooked", "Difference"]]

        # Execute Query
        transaction_query = """
            SELECT 
                k.name AS kitchen_name, 
                COALESCE(SUM(kt.subtotal), 0) AS amount_transferred, 
                COALESCE(SUM(kc.subtotal), 0) AS amount_cooked, 
                COALESCE(SUM(kt.subtotal), 0) - COALESCE(SUM(kc.subtotal), 0) AS difference
            FROM public.idil_kitchen_transfer kt
            INNER JOIN public.idil_kitchen_cook_process kc 
                ON kt.id = kc.kitchen_transfer_id
            INNER JOIN public.idil_kitchen k 
                ON k.id = kt.kitchen_id
            WHERE kt.state = 'processed' 
                AND kc.state = 'processed'
                AND kc.process_date BETWEEN %s AND %s
            GROUP BY k.name
            ORDER BY k.name;
        """

        self.env.cr.execute(transaction_query, (self.start_date, self.end_date))
        transactions = self.env.cr.fetchall()

        # Initialize grand totals
        total_transferred = 0
        total_cooked = 0
        total_difference = 0

        for transaction in transactions:
            kitchen_name = transaction[0] or ""
            amount_transferred = transaction[1] or 0
            amount_cooked = transaction[2] or 0
            difference = transaction[3] or 0

            # Accumulate totals
            total_transferred += amount_transferred
            total_cooked += amount_cooked
            total_difference += difference

            # Append data row
            data.append([
                kitchen_name,
                f"${amount_transferred:,.2f}",
                f"${amount_cooked:,.2f}",
                f"${difference:,.2f}",
            ])

        # Append Grand Total row
        data.append([
            "Grand Total",
            f"${total_transferred:,.2f}",
            f"${total_cooked:,.2f}",
            f"${total_difference:,.2f}",
        ])

        # Apply table styling and generate report as before

        # Table Styling and Insertion
        table = Table(data, colWidths=[200, 100, 100, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Golden brown for header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # White text for header
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align text
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold for header
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica'),  # Regular font for data
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Grand Total in bold
            ('FONTSIZE', (0, -1), (-1, -1), 12),  # Grand Total larger font
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9D9D9")),  # Light grey for Grand Total row
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),  # Black text for Grand Total row
        ]))

        elements.append(Spacer(1, 20))
        elements.append(table)

        # Build PDF
        doc.build(elements)

        # Save PDF as attachment
        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'kitchen_Summary_report',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
