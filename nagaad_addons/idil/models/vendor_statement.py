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
    _name = 'idil.vendor.statement'
    _description = 'Vendor Report Wizard'

    vendor_id = fields.Many2one(
        'idil.vendor.registration',
        string="Vendor Name",
        help="Filter transactions by Vendor Name"
        , required=True
    )
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def generate_pdf_report(self):
        # Query to fetch account details
        account_query = """
            SELECT code, name, currency_id, header_name
            FROM idil_chart_account
            WHERE id = 5
        """
        self.env.cr.execute(account_query, (self.vendor_id.id,))
        account_result = self.env.cr.fetchone()
        account_code = account_result[0] if account_result else "N/A"
        account_name = account_result[1] if account_result else "N/A"
        account_currency = account_result[2] if account_result else "N/A"
        account_type = account_result[3] if account_result else "N/A"

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
        date_partner_table = Table(
            [
                [
                    Paragraph(
                        f"<b>Partner:</b> {self.vendor_id.name}",
                        partner_align_style
                    )
                ]
            ],
            colWidths=[300],  # Set the width of the column (adjust as needed)
            style=[
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),  # Left-align the content
                ('LEFTPADDING', (0, 0), (-1, -1), 1),  # Add padding from the left
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),  # No padding on the right
                ('TOPPADDING', (0, 0), (-1, -1), 0),  # Adjust top padding if needed
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),  # Adjust bottom padding if needed
            ]
        )
        elements.append(date_partner_table)
        elements.append(Spacer(1, 12))

        # Balance Information
        # Add this query above the balance_info section to calculate balances dynamically

        # Calculate Opening Balance
        opening_balance_query = """
            SELECT 
                COALESCE(SUM(dr_amount - cr_amount), 0)
            FROM idil_transaction_bookingline tl
            INNER JOIN idil_transaction_booking tb ON tl.transaction_booking_id = tb.id
            WHERE tb.vendor_id = %s and account_display  like '2%%' AND tl.transaction_date < %s
        """
        self.env.cr.execute(opening_balance_query, (self.vendor_id.id, self.start_date))
        opening_balance_result = self.env.cr.fetchone()
        opening_balance = opening_balance_result[0] if opening_balance_result else 0.0

        # Calculate Total Debit and Credit within the specified date range
        debit_credit_query = """
            SELECT 
                COALESCE(SUM(dr_amount), 0) AS total_debit,
                COALESCE(SUM(cr_amount), 0) AS total_credit
            FROM idil_transaction_bookingline tl
            INNER JOIN idil_transaction_booking tb ON tl.transaction_booking_id = tb.id
            WHERE tb.vendor_id = %s and account_display  like '2%%' AND tl.transaction_date BETWEEN %s AND %s
        """
        self.env.cr.execute(debit_credit_query, (self.vendor_id.id, self.start_date, self.end_date))
        debit_credit_result = self.env.cr.fetchone()
        total_debit = debit_credit_result[0] if debit_credit_result else 0.0
        total_credit = debit_credit_result[1] if debit_credit_result else 0.0

        # Calculate Current Balance
        current_balance = opening_balance + total_debit - total_credit

        # Replace the hardcoded balance_info table with this
        balance_info = Table(
            [
                ["Opening Balance:", f"${opening_balance:,.2f}"],
                ["Debit:", f"${total_debit:,.2f}"],
                ["Credit:", f"${total_credit:,.2f}"],
                ["Balance:", f"${current_balance:,.2f}"],
            ],
            colWidths=[200, 100],  # Adjust the widths of the columns
            style=[
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),  # Right-align the first column
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),  # Right-align the second column
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ],
        )

        # Wrap the table to push it fully to the right
        balance_table_wrapper = Table(
            [[balance_info]],

            colWidths=[450],  # Push the entire table to the right edge
            style=[
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),  # Ensure the wrapper aligns to the right
                ('LEFTPADDING', (0, 0), (-1, -1), 0),  # No left padding
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),  # Align to the page's edge
            ],
        )

        elements.append(balance_table_wrapper)
        elements.append(Spacer(1, 12))

        # Table Header and Transactions
        data = [["Date", "Ref", "Debit", "Credit", "Balance"]]
        transaction_query = """
                     WITH transaction_totals AS (
                        SELECT 
                            tl.transaction_date, 
                            tb.reffno, 
                            SUM(COALESCE(tl.dr_amount, 0)) AS total_dr_amount, 
                            SUM(COALESCE(tl.cr_amount, 0)) AS total_cr_amount
                        FROM idil_transaction_bookingline tl
                        INNER JOIN idil_transaction_booking tb 
                            ON tl.transaction_booking_id = tb.id
                        WHERE 
                             tb.vendor_id = %s and account_display  like '2%%' 
                             AND tl.transaction_date BETWEEN %s AND %s
                        GROUP BY 
                            tl.transaction_date, 
                            tb.reffno
                    )
                    SELECT 
                        transaction_date, 
                        reffno, 
                        total_dr_amount, 
                        total_cr_amount, 
                        ABS(ROUND(CAST(SUM(total_dr_amount - total_cr_amount) OVER (
                            ORDER BY transaction_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) AS NUMERIC), 2)) AS running_balance
                    FROM transaction_totals
                    ORDER BY 
                        transaction_date, 
                        reffno;

               """

        self.env.cr.execute(transaction_query, (self.vendor_id.id, self.start_date, self.end_date))
        transactions = self.env.cr.fetchall()

        for transaction in transactions:
            data.append([
                transaction[0].strftime('%d/%m/%Y') if transaction[0] else "",
                transaction[1] or "",
                f"${transaction[2]:,.2f}" if transaction[2] else "$0.00",
                f"${transaction[3]:,.2f}" if transaction[3] else "$0.00",
                f"${transaction[4]:,.2f}" if transaction[4] else "$0.00",
            ])

        # Table Styling and Insertion
        table = Table(data, colWidths=[100, 200, 100, 100, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Golden brown background
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # White text for header
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align table text
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold header font
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica'),  # Regular font for data
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
            'name': 'Vendor_Statement.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
