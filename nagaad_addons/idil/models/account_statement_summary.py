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
    _name = 'transaction.report.wizard.summary'
    _description = 'Transaction Report Summary Wizard'

    account_number = fields.Many2one(
        'idil.chart.account',
        string="Account Number",
        help="Filter transactions by account number"
        , required=True
    )
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def generate_excel_report_summary(self):
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

        # Query to fetch transaction data grouped by date and account number
        transaction_query = """
            SELECT 
                transaction_date,
                (SELECT code FROM idil_chart_account WHERE id = account_number) AS account_number,
                ROUND(
                    CAST(
                        SUM(SUM(COALESCE(dr_amount, 0)) - SUM(COALESCE(cr_amount, 0))) OVER (
                            PARTITION BY account_number ORDER BY transaction_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) + %s AS NUMERIC
                    ), 2
                ) AS running_balance,
                SUM(COALESCE(dr_amount, 0)) AS total_debit,
                SUM(COALESCE(cr_amount, 0)) AS total_credit
            FROM 
                idil_transaction_bookingline
            WHERE 
                transaction_date BETWEEN %s AND %s
                AND account_number = 1
            GROUP BY 
                transaction_date, account_number
            ORDER BY 
                transaction_date;
        """
        self.env.cr.execute(transaction_query, (previous_balance, self.start_date, self.end_date))
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
        worksheet.merge_range('A1:E1', 'Account Statement --Summary Report', bold_centered)
        worksheet.merge_range('A2:E2', f'Date Range: {self.start_date} to {self.end_date}', bold_centered)

        # Write header row
        headers = ['Transaction Date', 'Account Number', 'Total Debit', 'Total Credit', 'Running Balance']
        for col, header in enumerate(headers):
            worksheet.write(3, col, header, header_format)

        # Write previous balance as the first row
        row_num = 4
        worksheet.write(row_num, 0, "Previous Balance", cell_format)  # No transaction date for previous balance
        worksheet.write(row_num, 1, self.account_number.code, cell_format)
        worksheet.write(row_num, 2, 0.0, currency_format)  # No debit amount
        worksheet.write(row_num, 3, 0.0, currency_format)  # No credit amount
        worksheet.write(row_num, 4, previous_balance, currency_format)  # Previous balance as running balance

        # Write transaction rows
        row_num += 1
        for transaction in transactions:
            worksheet.write(row_num, 0, transaction[0], cell_format)  # Transaction Date
            worksheet.write(row_num, 1, transaction[1], cell_format)  # Account Number
            worksheet.write(row_num, 2, transaction[3], currency_format)  # Total Debit
            worksheet.write(row_num, 3, transaction[4], currency_format)  # Total Credit
            worksheet.write(row_num, 4, transaction[2], currency_format)  # Running Balance
            # Update totals for debit and credit
            total_debit += transaction[3] if transaction[3] else 0.0
            total_credit += transaction[4] if transaction[4] else 0.0
            row_num += 1

        # Write totals row
        worksheet.write(row_num, 1, "Grand Total", bold_border)
        worksheet.write(row_num, 2, total_debit, bold_border)  # Total debit
        worksheet.write(row_num, 3, total_credit, bold_border)  # Total credit
        worksheet.write(row_num, 4, "", bold_border)  # No running balance for total row

        # Adjust column widths
        worksheet.set_column('A:A', 15)  # Transaction Date
        worksheet.set_column('B:B', 18)  # Account Number
        worksheet.set_column('C:C', 15)  # Total Debit
        worksheet.set_column('D:D', 15)  # Total Credit
        worksheet.set_column('E:E', 15)  # Running Balance

        workbook.close()
        output.seek(0)

        # Encode the Excel file as Base64
        excel_data = base64.b64encode(output.read()).decode('utf-8')
        output.close()

        # Create an attachment
        attachment = self.env['ir.attachment'].create({
            'name': 'Account_Statement_summary.xlsx',
            'type': 'binary',
            'datas': excel_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }

    def generate_pdf_report_summary(self):
        # Query to fetch account details
        account_query = """
            SELECT code, name, currency_id, header_name
            FROM idil_chart_account
            WHERE id = %s
        """
        self.env.cr.execute(account_query, (self.account_number.id,))
        account_result = self.env.cr.fetchone()
        account_code = account_result[0] if account_result else "N/A"
        account_name = account_result[1] if account_result else "N/A"
        account_currency = account_result[2] if account_result else "N/A"
        account_type = account_result[3] if account_result else "N/A"

        # Calculate the previous balance
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

        # Create PDF document in landscape format
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=30,
            leftMargin=30,
            topMargin=40,
            bottomMargin=30,
        )
        elements = []

        # Add title and header details
        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        title_style.alignment = 1  # Center alignment
        title = Paragraph("<b>Nagaad Account Statement's -- Summary Report</b>", title_style)

        subtitle_style = styles["Normal"]
        subtitle_style.alignment = 1
        subtitle = Paragraph(
            f"From Transaction Date: <b>{self.start_date.strftime('%m/%d/%Y') if self.start_date else 'N/A'}</b> "
            f"| To Transaction Date: <b>{self.end_date.strftime('%m/%d/%Y') if self.end_date else 'N/A'}</b>",
            subtitle_style
        )

        account_info_style = styles["Normal"]
        account_info_style.alignment = 1
        account_info = Paragraph(
            f"Account No: <b>{account_code}</b> | Account Name: <b>{account_name}</b><br/>"
            f"Currency ID: <b>{account_currency}</b> | Account Type: <b>{account_type}</b>",
            account_info_style
        )

        elements.extend([title, subtitle, account_info])

        # Footer details
        current_user = self.env.user.name
        current_datetime = datetime.now().strftime('%d-%b-%Y %H:%M:%S')
        footer_style = styles["Normal"]
        footer_style.fontSize = 10
        footer_style.alignment = 2  # Right alignment
        footer = Paragraph(
            f"<b>Printed By:</b> {current_user}<br/><b>Report Printed Date:</b> {current_datetime}",
            footer_style
        )
        elements.append(Spacer(1, 12))
        elements.append(footer)

        # Query to fetch grouped transactions
        transaction_query = """
            SELECT
                transaction_date,
                SUM(COALESCE(dr_amount, 0)) AS total_debit,
                SUM(COALESCE(cr_amount, 0)) AS total_credit,
                ROUND(
                    CAST(
                        SUM(SUM(COALESCE(dr_amount, 0)) - SUM(COALESCE(cr_amount, 0))) OVER (
                            ORDER BY transaction_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) AS NUMERIC
                    ), 2
                ) AS running_balance
            FROM
                idil_transaction_bookingline
            WHERE
                transaction_date BETWEEN %s AND %s
                AND account_number = %s
            GROUP BY
                transaction_date
            ORDER BY
                transaction_date
        """
        self.env.cr.execute(transaction_query, (self.start_date, self.end_date, self.account_number.id))
        transactions = self.env.cr.fetchall()

        # Prepare data for the table
        data = [["Transaction Date", "Total Debit", "Total Credit", "Running Balance"]]

        # Add the previous balance as the first row
        data.append([
            "Previous Balance", "", "", f"{previous_balance:,.2f}"
        ])

        # Add transaction rows
        for transaction in transactions:
            data.append([
                transaction[0].strftime('%m/%d/%Y') if transaction[0] else "",
                f"{transaction[1]:,.2f}" if transaction[1] else "0.00",
                f"{transaction[2]:,.2f}" if transaction[2] else "0.00",
                f"{transaction[3]:,.2f}" if transaction[3] else "0.00",
            ])

        # Calculate grand totals
        total_debit = sum(row[1] for row in transactions if row[1])
        total_credit = sum(row[2] for row in transactions if row[2])
        data.append([
            "Grand Total", f"{total_debit:,.2f}", f"{total_credit:,.2f}", ""
        ])

        # Create and style the table
        table = Table(data, colWidths=[200, 160, 160, 200])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Header background
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # Header text color
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Add grid lines
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center-align all columns
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Vertically align to the middle
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold font for header
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Bold font for totals
        ]))

        elements.append(table)

        # Build the PDF document
        doc.build(elements)

        # Save the PDF as an attachment
        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Account_Statement_Summary_Report.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'new',
        }
