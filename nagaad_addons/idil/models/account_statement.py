from datetime import datetime

from odoo import models, fields, api
from odoo.exceptions import UserError
import io
import base64

import xlsxwriter

from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

from odoo.fields import Image


class TransactionReportWizard(models.TransientModel):
    _name = 'transaction.report.wizard'
    _description = 'Transaction Report Wizard'

    account_number = fields.Many2one(
        'idil.chart.account',
        string="Account Number",
        help="Filter transactions by account number"
        , required=True
    )
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def generate_excel_report(self):
        # Query to compute the previous balance
        previous_balance_query = """
            SELECT 
                SUM(COALESCE(dr_amount, 0)) - SUM(COALESCE(cr_amount, 0)) AS previous_balance
            FROM 
                idil_transaction_bookingline
            WHERE 
                transaction_date < %s
                AND account_number = %s
        """
        self.env.cr.execute(previous_balance_query, (self.start_date, self.account_number.id))
        previous_balance_result = self.env.cr.fetchone()
        previous_balance = previous_balance_result[0] if previous_balance_result and previous_balance_result[
            0] is not None else 0.0

        # Query to fetch transaction data
        transaction_query = """
            SELECT 
                transaction_date,
                (SELECT code FROM idil_chart_account WHERE id = account_number) AS account_number,
                transaction_booking_id,
                description,
                account_display,
                dr_amount,
                cr_amount,
                ROUND(
                    CAST(
                        SUM(COALESCE(dr_amount, 0) - COALESCE(cr_amount, 0)) OVER (
                            ORDER BY transaction_date, transaction_booking_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) + %s AS NUMERIC
                    ), 2
                ) AS running_balance
            FROM 
                idil_transaction_bookingline
            WHERE 
                transaction_date BETWEEN %s AND %s
                AND account_number = %s
            ORDER BY 
                transaction_date, transaction_booking_id
        """
        self.env.cr.execute(transaction_query,
                            (previous_balance, self.start_date, self.end_date, self.account_number.id))
        transactions = self.env.cr.fetchall()

        # Initialize totals
        total_debit = 0.0
        total_credit = 0.0

        # Create an Excel file in memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Account Statement')

        # Define formats
        bold = workbook.add_format({'bold': True})
        bold_centered = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})
        header_format = workbook.add_format({'bold': True, 'align': 'center', 'border': 1, 'bg_color': '#D3D3D3'})
        cell_format = workbook.add_format({'border': 1})
        bold_border = workbook.add_format({'bold': True, 'border': 1})
        currency_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})

        # Write the report title
        worksheet.merge_range('A1:H1', 'Account Statement', bold_centered)
        worksheet.merge_range('A2:H2', f'Date Range: {self.start_date} to {self.end_date}', bold_centered)

        # Write header row
        headers = ['Transaction Date', 'Account Number', 'Transaction ID', 'Description', 'Account Display',
                   'Debit Amount',
                   'Credit Amount', 'Running Balance']
        for col, header in enumerate(headers):
            worksheet.write(3, col, header, header_format)

        # Write previous balance as the first row
        row_num = 4
        worksheet.write(row_num, 0, "N/A", cell_format)  # No transaction date for previous balance
        worksheet.write(row_num, 1, self.account_number.code, cell_format)
        worksheet.write(row_num, 2, "N/A", cell_format)  # No transaction ID for previous balance
        worksheet.write(row_num, 3, "Previous Balance", cell_format)
        worksheet.write(row_num, 4, "", cell_format)  # No account display for previous balance
        worksheet.write(row_num, 5, 0.0, currency_format)  # No debit amount
        worksheet.write(row_num, 6, 0.0, currency_format)  # No credit amount
        worksheet.write(row_num, 7, previous_balance, currency_format)  # Previous balance as running balance

        # Write transaction rows
        row_num += 1
        for transaction in transactions:
            for col_num, value in enumerate(transaction):
                format_to_use = currency_format if col_num in [5, 6, 7] else cell_format
                worksheet.write(row_num, col_num, value, format_to_use)
            # Update totals for debit and credit
            total_debit += transaction[5] if transaction[5] else 0.0
            total_credit += transaction[6] if transaction[6] else 0.0
            row_num += 1

        # Write totals row
        worksheet.write(row_num, 4, "Grand Total", bold_border)
        worksheet.write(row_num, 5, total_debit, bold_border)  # Total debit
        worksheet.write(row_num, 6, total_credit, bold_border)  # Total credit
        worksheet.write(row_num, 7, "", bold_border)  # No running balance for total row

        # Adjust column widths
        worksheet.set_column('A:A', 15)  # Transaction Date
        worksheet.set_column('B:B', 18)  # Account Number
        worksheet.set_column('C:C', 15)  # Transaction ID
        worksheet.set_column('D:D', 30)  # Description
        worksheet.set_column('E:E', 20)  # Account Display
        worksheet.set_column('F:H', 15)  # Debit, Credit, Running Balance

        workbook.close()
        output.seek(0)

        # Encode the Excel file as Base64
        excel_data = base64.b64encode(output.read()).decode('utf-8')
        output.close()

        # Create an attachment
        attachment = self.env['ir.attachment'].create({
            'name': 'Account_Statement.xlsx',
            'type': 'binary',
            'datas': excel_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    import io
    import base64

    def generate_pdf_report(self):
        # Query to compute the previous balance
        previous_balance_query = """
            SELECT
                SUM(COALESCE(dr_amount, 0)) - SUM(COALESCE(cr_amount, 0)) AS previous_balance
            FROM
                idil_transaction_bookingline
            WHERE
                transaction_date < %s
                AND account_number = %s
        """
        self.env.cr.execute(previous_balance_query, (self.start_date, self.account_number.id))
        previous_balance_result = self.env.cr.fetchone()
        previous_balance = previous_balance_result[0] if previous_balance_result and previous_balance_result[
            0] is not None else 0.0

        # Query to fetch transaction data
        transaction_query = """
            SELECT
                transaction_date,
                 (SELECT code FROM idil_chart_account WHERE id = account_number) AS account_number,
                transaction_booking_id,
                description,
                account_display,
                dr_amount,
                cr_amount,
                ROUND(
                    CAST(
                        SUM(COALESCE(dr_amount, 0) - COALESCE(cr_amount, 0)) OVER (
                            ORDER BY transaction_date, transaction_booking_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) + %s AS NUMERIC
                    ), 2
                ) AS running_balance
            FROM
                idil_transaction_bookingline
            WHERE
                transaction_date BETWEEN %s AND %s
                AND account_number = %s
            ORDER BY
                transaction_date, transaction_booking_id
        """
        self.env.cr.execute(transaction_query,
                            (previous_balance, self.start_date, self.end_date, self.account_number.id))
        transactions = self.env.cr.fetchall()

        if not transactions:
            raise UserError("No data found for the selected criteria.")

        # Initialize totals
        total_debit = sum(row[5] for row in transactions if row[5])
        total_credit = sum(row[6] for row in transactions if row[6])

        # Create PDF document in landscape format
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=40,
                                bottomMargin=30)
        elements = []

        # Add logo
        logo_path = "/path/to/logo.jpg"  # Replace with the actual path to your logo file
        try:
            logo = Image(logo_path, 2 * inch, 1 * inch)
            elements.append(logo)
        except Exception:
            pass

        # Add title with formatted transaction dates
        title_style = getSampleStyleSheet()["Title"]
        title_style.alignment = 1  # Center alignment
        title_style.fontSize = 16
        title_style.leading = 20
        title_style.textColor = colors.black

        subtitle_style = getSampleStyleSheet()["Normal"]
        subtitle_style.alignment = 1  # Center alignment
        subtitle_style.fontSize = 12
        subtitle_style.textColor = colors.black

        # Main title
        title = Paragraph("<b>Nagaad Account Statement's Report</b>", title_style)

        # Subtitle with transaction date range
        subtitle = Paragraph(
            f"From Transaction Date: <b>{self.start_date.strftime('%m/%d/%Y') if self.start_date else 'N/A'}</b> "
            f"| To Transaction Date: <b>{self.end_date.strftime('%m/%d/%Y') if self.end_date else 'N/A'}</b>",
            subtitle_style
        )

        elements.append(title)
        elements.append(subtitle)
        elements.append(Spacer(1, 20))

        # Get current user and print date
        current_user = self.env.user.name
        current_datetime = datetime.now().strftime('%d-%b-%y %H:%M:%S')

        # Add printed by and print date info
        footer_style = getSampleStyleSheet()["Normal"]
        footer_style.fontSize = 10
        footer_style.alignment = 2  # Right alignment

        footer_text = Paragraph(
            f"<b>PrintBy:</b> {current_user}<br/><b>PrintDate:</b> {current_datetime}",
            footer_style
        )

        # Add the footer to the elements list
        elements.append(Spacer(1, 12))  # Add some space before the footer
        elements.append(footer_text)

        # Table header
        data = [
            ["Transaction Date", "Account Number", "Transaction ID", "Description", "Account Display", "Debit Amount",
             "Credit Amount", "Running Balance"],
            ["", self.account_number.code, "N/A", "Previous Balance", "", f"{0.0:,.2f}", f"{0.0:,.2f}",
             f"{previous_balance:,.2f}"],
        ]

        # Add transaction rows
        for transaction in transactions:
            data.append([
                transaction[0].strftime('%m/%d/%Y') if transaction[0] else "",
                transaction[1] or "",
                transaction[2] or "",
                transaction[3] or "",
                transaction[4] or "",
                f"{transaction[5]:,.2f}" if transaction[5] else "0.00",
                f"{transaction[6]:,.2f}" if transaction[6] else "0.00",
                f"{transaction[7]:,.2f}" if transaction[7] else "0.00",
            ])

        # Add totals row
        data.append([
            "", "", "Grand Total", "", "", f"{total_debit:,.2f}", f"{total_credit:,.2f}", "",
        ])

        # Create a table with styling
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Header background
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # Header text color
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, colors.black),  # Bold line below header
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.black),  # Bold line below totals
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center-align text
            ('ALIGN', (5, 1), (-1, -1), 'RIGHT'),  # Right-align numeric columns
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold font for header
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Bold font for totals
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),  # Regular font for rows
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Light grid lines for table
        ]))

        elements.append(table)
        doc.build(elements)

        # Save the PDF to an attachment
        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Account_Statement_Attractive.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }
