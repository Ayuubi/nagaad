from odoo import models, fields, api
import xlsxwriter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import base64
from datetime import datetime


class VendorTransactionReportWizard(models.TransientModel):
    _name = 'idil.vendor.balance.list.report'
    _description = 'Vendor Report with Items Wizard'

    end_date = fields.Date(string="As of Date", required=True)

    def generate_pdf_report(self):

        # Fetch active company logo and details
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
            pagesize=letter,  # Set the page orientation to portrait
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
            f"<b>As of Date :</b> {self.end_date.strftime('%d/%m/%Y')}<br/>",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # Correctly ordered table headers
        data = [
            ["Vendor Name", "Phone", "Debit", "Credit", "Balance"]
        ]

        # Fetch transactions from the database
        transaction_query = """                      
                SELECT  
                    vr.name,
                    vr.phone,
                    SUM(dr_amount) AS dr_amount,
                    SUM(cr_amount) AS cr_amount,
                    SUM(dr_amount) - SUM(cr_amount) AS running_balance
                FROM idil_transaction_bookingline tl
                INNER JOIN idil_transaction_booking tb ON tl.transaction_booking_id = tb.id
                INNER JOIN idil_vendor_registration vr ON tb.vendor_id = vr.id 
                WHERE 
                    account_display LIKE '2%%' 
                    AND tl.transaction_date <= %s
                GROUP BY vr.name, vr.phone;
        """
        self.env.cr.execute(transaction_query, (self.end_date,))  # Wrap end_date in a tuple
        transactions = self.env.cr.fetchall()

        # Add data rows to the table
        for transaction in transactions:
            data.append([
                transaction[0] or "",  # Vendor Name
                transaction[1] or "Vendor Payment",  # Phone
                f"${float(transaction[2]):,.2f}" if transaction[2] else "$0.00",  # Debit
                f"${float(transaction[3]):,.2f}" if transaction[3] else "$0.00",  # Credit
                f"${float(transaction[4]):,.2f}" if transaction[4] else "$0.00",  # Balance
            ])

        # Table Styling and Insertion
        table = Table(data, colWidths=[200, 100, 80, 80, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Header background color
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # Header text color
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center-align all cells by default
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold header font
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica'),  # Regular font for data
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Vertical alignment
            ('LEFTPADDING', (0, 0), (-1, -1), 5),  # Add padding for readability
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))

        # Add table to the PDF
        elements.append(Spacer(1, 20))
        elements.append(table)

        # Build PDF
        doc.build(elements)

        # Save PDF as attachment
        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Vendor Balance Report.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
