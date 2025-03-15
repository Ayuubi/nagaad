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
    _name = 'idil.daily.event.cost.profit'
    _description = 'Daily Event Cost Profit Report'

    year = fields.Integer(string="Year", required=True, default=2025)
    month = fields.Integer(string="Month", required=True, default=3)

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
            f"<b>Year:</b> {self.year}, <b>Month:</b> {self.month}<br/>",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # Correctly ordered table headers
        data = [
            ["Event Date", "Kitchen Entries", "Revenue", "Cost", "Profit"]
        ]

        # Initialize grand totals
        total_kitchen_entries = 0
        total_revenue = 0.0
        total_cost = 0.0
        total_profit = 0.0

        # Fetch transactions from the database
        transaction_query = """                      
                    WITH hall_booking_aggregated AS (
                        SELECT DATE(hb.start_time) AS Event_Date, 
                               SUM(hb.total_price) AS Total_Price,
                               SUM(COALESCE(hb.extra_service_amount, 0)) AS Extra_Service_Amount
                        FROM idil_hall_booking hb
                        INNER JOIN idil_customer_registration c ON c.id = hb.customer_id
                        WHERE EXTRACT(MONTH FROM hb.start_time) = %s
                          AND EXTRACT(YEAR FROM hb.start_time) = %s
                        GROUP BY DATE(hb.start_time)
                    )
                    SELECT hba.Event_Date, 
                           COUNT(kcp.id) AS Kitchen_Entries,  -- Count kitchen records
                           hba.Total_Price + hba.Extra_Service_Amount AS Revenue,
                           SUM(kcp.subtotal) AS Cost,
                           (hba.Total_Price + hba.Extra_Service_Amount) - SUM(kcp.subtotal) AS Profit
                    FROM hall_booking_aggregated hba
                    LEFT JOIN idil_kitchen_cook_process kcp
                        ON hba.Event_Date = DATE(kcp.process_date)
                    INNER JOIN public.idil_kitchen_transfer kt
                        ON kt.id = kcp.kitchen_transfer_id
                    INNER JOIN public.idil_kitchen k
                        ON k.id = kt.kitchen_id
                    WHERE k.is_event = TRUE
                    GROUP BY hba.Event_Date, hba.Total_Price, hba.Extra_Service_Amount
                    ORDER BY hba.Event_Date;
            """
        self.env.cr.execute(transaction_query, (self.month, self.year))
        transactions = self.env.cr.fetchall()

        # Add data rows to the table
        for transaction in transactions:
            total_kitchen_entries += transaction[1]
            total_revenue += transaction[2]
            total_cost += transaction[3]
            total_profit += transaction[4]

            data.append([
                transaction[0] or "",  # Event Date
                transaction[1] or 0,  # Kitchen Entries
                f"${transaction[2]:,.2f}",  # Revenue
                f"${transaction[3]:,.2f}",  # Cost
                f"${transaction[4]:,.2f}"  # Profit
            ])

        # Add grand totals row
        data.append([
            "Grand Total",  # Label
            total_kitchen_entries,  # Total Kitchen Entries
            f"${total_revenue:,.2f}",  # Total Revenue
            f"${total_cost:,.2f}",  # Total Cost
            f"${total_profit:,.2f}"  # Total Profit
        ])

        # Table Styling and Insertion
        table = Table(data, colWidths=[100, 100, 100, 100, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Header background color
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # Header text color
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center-align all cells
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Bold font for grand totals
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#F0F0F0")),  # Light background for totals
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
            'name': 'Daily Event Cost Profit Report.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
