from odoo import models, fields, api
import xlsxwriter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import base64
from datetime import datetime


class VendorSummaryReportWizard(models.TransientModel):
    _name = 'idil.stock.summary.report'
    _description = 'Stock Summary Report'

    end_date = fields.Date(string="Os Of Date", required=True)

    def generate_pdf_report(self):
        # Fetch active company details
        company = self.env.company
        company_logo = company.logo if company.logo else None
        company_name = company.name or "Your Company"
        company_address = f"{company.partner_id.city or ''}, {company.partner_id.country_id.name or ''}"
        company_phone = company.partner_id.phone or "N/A"
        company_email = company.partner_id.email or "N/A"
        company_website = company.website or "N/A"

        # Create PDF document
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=40,
                                bottomMargin=30)
        elements = []

        # Styles
        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(name='Header', parent=styles['Title'], fontSize=18,
                                      textColor=colors.HexColor("#B6862D"), alignment=1)
        subtitle_style = ParagraphStyle(name='Subtitle', parent=styles['Normal'], fontSize=12, alignment=1)
        left_align_style = ParagraphStyle(name='LeftAlign', parent=styles['Normal'], fontSize=12, alignment=0)

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
            f"<b>As Of Date:</b> {self.end_date.strftime('%d/%m/%Y')}",
            left_align_style))
        elements.append(Spacer(1, 12))

        # Fetch Transactions
        transaction_query = """
                SELECT 
                      i.name AS "Item Name",
                      COALESCE(SUM(pl.quantity), 0) AS "Opening Stock",
                      COALESCE(SUM(kcl.transfer_qty), 0) AS "Transferred to Kitchen",
                      COALESCE(SUM(
                          CASE 
                              WHEN kcp.state = 'processed' THEN kcl.cooked_qty
                              ELSE 0
                          END
                      ), 0) AS "Used Items (Cooked Qty)",
                      COALESCE(SUM(pl.quantity), 0) - COALESCE(SUM(
                          CASE 
                              WHEN kcp.state = 'processed' THEN kcl.cooked_qty
                              ELSE 0
                          END
                      ), 0) AS "Closing Stock"
                    FROM 
                      idil_item i
                    LEFT JOIN 
                      idil_purchase_order_line pl ON i.id = pl.item_id
                    LEFT JOIN 
                      idil_purchase_order po ON po.id = pl.order_id
                    LEFT JOIN 
                      idil_kitchen_cook_line kcl ON kcl.item_id = i.id
                    LEFT JOIN 
                      idil_kitchen_cook_process kcp ON kcp.id = kcl.cook_process_id
                    WHERE 
                      i.item_type = 'inventory'
                      AND po.purchase_date <= %s
                      AND po.status ='approved'
                    GROUP BY 
                      i.name
                    ORDER BY 
                      i.name;
    
        """
        self.env.cr.execute(transaction_query, (self.end_date,))

        transactions = self.env.cr.fetchall()

        # Initialize grand total variables
        grand_total_quantity = 0
        grand_total_balance = 0

        # Table Header
        data = [["No", "Item Name", "Opening Stock", "Transferred", "Used Items", "Closing Stock"]]

        # Add transaction data
        counter = 1
        for row in transactions:
            item_name = row[0] or "N/A"
            opening_stock = row[1] or 0
            transferred = row[2] or 0
            used_qty = row[3] or 0
            closing_stock = row[4] or 0

            data.append([
                counter,
                item_name,
                f"{opening_stock} kg",
                f"{transferred} kg",
                f"{used_qty} kg",
                f"{closing_stock} kg"
            ])
            counter += 1

        # Append Grand Total Row
        data.append([
            "Total", "", grand_total_quantity, f"${grand_total_balance:,.2f}"
        ])

        # Table Styling
        table = Table(data, colWidths=[80, 220, 100, 120])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Header color
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # Header text color
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center-align all cells
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold header font
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),  # Regular font for data
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Vertical alignment
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            # Styling for Grand Total Row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#FFD700")),  # Gold background
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),  # Black text
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Bold font
        ]))

        elements.append(Spacer(1, 20))
        elements.append(table)

        # Build and Save PDF
        doc.build(elements)
        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'StockSummaryReport.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
