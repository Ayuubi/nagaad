from odoo import models, fields, api
from odoo.exceptions import UserError
import io
import base64

import xlsxwriter

from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import letter
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
        self.env.cr.execute(transaction_query, (previous_balance, self.start_date, self.end_date, self.account_number.id))
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
                account_number,
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
        self.env.cr.execute(transaction_query, (previous_balance, self.start_date, self.end_date, self.account_number.id))
        transactions = self.env.cr.fetchall()

        if not transactions:
            raise UserError("No data found for the selected criteria.")

        # Initialize totals
        total_debit = sum(row[5] for row in transactions if row[5])
        total_credit = sum(row[6] for row in transactions if row[6])

        # Create PDF document
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=40, bottomMargin=30)
        elements = []

        # Title and subtitle
        styles = getSampleStyleSheet()
        title_style = styles['Title']
        title_style.alignment = 1  # Center alignment
        title = Paragraph("<b>Account Statement</b>", title_style)

        subtitle = Paragraph(
            f"<b>Date Range:</b> {self.start_date} to {self.end_date}",
            styles['Normal']
        )

        elements.append(title)
        elements.append(subtitle)
        elements.append(Paragraph("<br/>", styles['Normal']))

        # Table header
        data = [
            ["Date", "Transaction No", "Memo/Description", "Account Full Name", "Credit", "Debit", "Balance"],
            ["", "", "Previous Balance", "", f"{0.0:,.2f}", f"{0.0:,.2f}", f"{previous_balance:,.2f}"],
        ]

        # Add transaction rows
        for transaction in transactions:
            data.append([
                transaction[0].strftime('%m/%d/%Y') if transaction[0] else "",
                transaction[2] or "",
                transaction[3] or "",
                transaction[4] or "",
                f"{transaction[6]:,.2f}" if transaction[6] else "0.00",
                f"{transaction[5]:,.2f}" if transaction[5] else "0.00",
                f"{transaction[7]:,.2f}" if transaction[7] else "0.00",
            ])

        # Add totals row
        data.append([
            "", "", "Grand Total", "", f"{total_credit:,.2f}", f"{total_debit:,.2f}", "",
        ])

        # Create a table without specifying static column widths
        table = Table(data)
        table.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.black),  # Bold line below header
            ('LINEBELOW', (0, -1), (-1, -1), 2, colors.black),  # Bold line below totals
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align all text
            ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),  # Right-align numeric columns
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold font for header
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Bold font for totals
            ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),  # Regular font for rows
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),  # Light grey background for header
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Light grid lines for table
        ]))

        elements.append(table)
        doc.build(elements)

        # Save the PDF to an attachment
        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Account_Statement.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }
