from odoo import models, fields, api
import xlsxwriter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import base64
from datetime import datetime


class Kitchen_ReportWizard(models.TransientModel):
    _name = 'idil.kitchen.cooked.report'
    _description = 'Kitchen Report Wizard'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def generate_pdf_report(self):
        company = self.env.company
        company_logo = company.logo if company.logo else None
        company_name = company.name or "Your Company"
        company_address = f"{company.partner_id.city or ''}, {company.partner_id.country_id.name or ''}"
        company_phone = company.partner_id.phone or "N/A"
        company_email = company.partner_id.email or "N/A"
        company_website = company.website or "N/A"

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

        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            name='Header',
            parent=styles['Title'],
            fontSize=18,
            textColor=colors.HexColor("#B6862D"),
            alignment=1
        )
        subtitle_style = ParagraphStyle(
            name='Subtitle',
            parent=styles['Normal'],
            fontSize=12,
            alignment=1
        )
        left_align_style = ParagraphStyle(
            name='LeftAlign',
            parent=styles['Normal'],
            fontSize=12,
            alignment=0
        )

        # Logo
        if company_logo:
            logo_image = Image(io.BytesIO(base64.b64decode(company_logo)), width=120, height=60)
            elements.append(logo_image)
        else:
            elements.append(Paragraph("<b>No Logo Available</b>", header_style))

        elements.append(Spacer(1, 12))

        # Company details
        company_name_paragraph = Paragraph(f"<b>{company_name.upper()}</b>", header_style)
        company_details_paragraph = Paragraph(
            f"{company_address}<br/>"
            f"Phone No.: {company_phone}<br/>"
            f"Email: {company_email}<br/>"
            f"Web: {company_website}",
            subtitle_style
        )

        # Report title
        report_title = Paragraph("<b>LIST OF ITEMS COOKED REPORT</b>", header_style)

        elements.extend([
            company_name_paragraph,
            Spacer(1, 6),
            company_details_paragraph,
            Spacer(1, 12),
            report_title,
            Spacer(1, 20)
        ])

        # Date range
        date_range = Paragraph(
            f"<b>Date from:</b> {self.start_date.strftime('%d/%m/%Y')}<br/>"
            f"<b>Date to:</b> {self.end_date.strftime('%d/%m/%Y')}<br/>",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # Table header
        data = [["Item Name", "Cooked Qty", "Unit Price", "Cooked Amount"]]

        # New query
        transaction_query = """
            SELECT 
                i.name,
                kc.cooked_qty,
                kc.unit_price,
                kc.cooked_amount
            FROM public.idil_kitchen_cook_line kc
            INNER JOIN public.idil_item i 
                ON kc.item_id = i.id
            INNER JOIN public.idil_kitchen_cook_process kcp 
                ON kc.cook_process_id = kcp.id
            WHERE kcp.state = 'processed'
              AND kcp.process_date BETWEEN %s AND %s
            ORDER BY i.name
        """

        self.env.cr.execute(transaction_query, (self.start_date, self.end_date))
        transactions = self.env.cr.fetchall()

        total_cooked_qty = 0
        total_cooked_amount = 0

        for transaction in transactions:
            item_name = transaction[0] or ""
            cooked_qty = transaction[1] or 0
            unit_price = transaction[2] or 0
            cooked_amount = transaction[3] or 0

            total_cooked_qty += cooked_qty
            total_cooked_amount += cooked_amount

            data.append([
                item_name,
                f"{cooked_qty:,.2f}",
                f"${unit_price:,.2f}",
                f"${cooked_amount:,.2f}",
            ])

        # Grand total row
        data.append([
            "Grand Total",
            f"{total_cooked_qty:,.2f}",
            "",
            f"${total_cooked_amount:,.2f}",
        ])

        # Table
        table = Table(data, colWidths=[220, 100, 100, 120])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTSIZE', (0, -1), (-1, -1), 11),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9D9D9")),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        elements.append(Spacer(1, 20))
        elements.append(table)

        doc.build(elements)

        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'list_of_items_cooked_report.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }