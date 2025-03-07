from odoo import models, fields, api
import xlsxwriter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import base64
from datetime import datetime


class ItemSummaryReportWizard(models.TransientModel):
    _name = 'idil.item.summary.with.vendor'
    _description = 'Item Summary Report with Vendor Wizard'

    vendor_id = fields.Many2one(
        'idil.vendor.registration',
        string="Vendor Name",
        help="Filter transactions by Vendor Name"
        , required=True
    )
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def generate_pdf_report(self):
        # Fetch active company logo and details
        company = self.env.company
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
            pagesize=landscape(letter),
            rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=30,
        )
        elements = []

        # Styles
        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            name='Header', parent=styles['Title'], fontSize=18, textColor=colors.HexColor("#B6862D"), alignment=1
        )
        subtitle_style = ParagraphStyle(
            name='Subtitle', parent=styles['Normal'], fontSize=12, alignment=1
        )
        left_align_style = ParagraphStyle(
            name='LeftAlign', parent=styles['Normal'], fontSize=12, alignment=0
        )

        # Add company logo
        if company_logo:
            logo_image = Image(io.BytesIO(base64.b64decode(company_logo)), width=120, height=60)
            elements.append(logo_image)
        else:
            elements.append(Paragraph("<b>No Logo Available</b>", header_style))

        elements.append(Spacer(1, 12))

        # Add company details
        elements.extend([
            Paragraph(f"<b>{company_name.upper()}</b>", header_style),
            Spacer(1, 6),
            Paragraph(
                f"{company_address}<br/>Phone: {company_phone}<br/>Email: {company_email}<br/>Web: {company_website}",
                subtitle_style),
            Spacer(1, 20)
        ])

        # Add Date Range and Vendor Information
        elements.append(Paragraph(
            f"<b>Date from:</b> {self.start_date.strftime('%d/%m/%Y')}<br/><b>Date to:</b> {self.end_date.strftime('%d/%m/%Y')}",
            left_align_style))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"<b>Partner:</b> {self.vendor_id.name}", left_align_style))
        elements.append(Spacer(1, 12))

        # Fetch Transactions using updated query
        transaction_query = """
            SELECT  
                tb.vendor_id,
                it.name AS item_name,
                tl.item_id,
                SUM(pl.quantity) AS total_quantity,
                AVG(pl.cost_price) AS avg_cost_price,
                SUM(pl.quantity) * AVG(pl.cost_price) AS total_balance
            FROM idil_transaction_bookingline tl
            INNER JOIN idil_transaction_booking tb ON tl.transaction_booking_id = tb.id
            INNER JOIN idil_vendor_registration vr ON tb.vendor_id = vr.id
            LEFT JOIN idil_item it ON it.id = tl.item_id
            LEFT JOIN idil_purchase_order_line pl ON pl.id = tl.order_line
            WHERE tb.vendor_id = %s 
            AND tl.transaction_date BETWEEN %s AND %s
            GROUP BY it.name, tl.item_id, tb.vendor_id
            ORDER BY tb.vendor_id, tl.item_id ASC
        """
        self.env.cr.execute(transaction_query, (self.vendor_id.id, self.start_date, self.end_date))
        transactions = self.env.cr.fetchall()

        # Table Header
        data = [
            ["Vendor ID", "Item Name", "Item ID", "Quantity", "Cost Price", "Balance"]
        ]

        # Add transaction data
        for transaction in transactions:
            vendor_id = transaction[0] or "N/A"
            item_name = transaction[1] or "N/A"
            item_id = transaction[2] or "N/A"
            quantity = transaction[3] or 0
            cost_price = f"${float(transaction[4]):,.2f}" if transaction[4] else "$0.00"
            balance = f"${float(transaction[5]):,.2f}" if transaction[5] else "$0.00"

            data.append([vendor_id, item_name, item_id, quantity, cost_price, balance])

        # Table Styling
        table = Table(data, colWidths=[80, 150, 80, 80, 80, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))

        elements.append(Spacer(1, 20))
        elements.append(table)

        # Build and Save PDF
        doc.build(elements)
        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'ItemSummaryReportByVendor.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
