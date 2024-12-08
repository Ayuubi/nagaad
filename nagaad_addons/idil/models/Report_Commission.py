import io
import base64
import xlsxwriter
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

from odoo import models, fields, api
import logging

# Define the logger
_logger = logging.getLogger(__name__)


class CommissionReportWizard(models.TransientModel):
    _name = 'commission.report.wizard'
    _description = 'Commission Report Wizard'

    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    cashier = fields.Many2one('res.users', string="Cashier", required=False)

    def generate_commission_report(self):
        """Generate the commission report based on wizard inputs."""
        self.ensure_one()
        # Call the function to generate the report
        return self.env['commission.report'].generate_report(self.start_date, self.end_date,
                                                             self.cashier.id if self.cashier else None)

    def generate_report_pdf(self):
        """Generate the commission report based on wizard inputs."""
        self.ensure_one()
        # Call the function to generate the report
        return self.env['commission.report'].generate_report_pdf(self.start_date, self.end_date,
                                                                 self.cashier.id if self.cashier else None)


class CommissionReport(models.AbstractModel):
    _name = 'commission.report'
    _description = 'Commission Report'

    def generate_report(self, start_date, end_date, cashier_id=None, export_type="excel"):
        # Build the WHERE clause dynamically
        where_clauses = ["tb.trx_date BETWEEN %s AND %s"]
        params = [start_date, end_date]

        if cashier_id:
            where_clauses.append("po.cashier = %s")
            params.append(cashier_id)

        # Combine all WHERE clauses
        where_clause = " AND ".join(where_clauses)

        # Query with dynamic filters
        query = f"""
            SELECT 
                po.cashier, 
                SUM(tb.amount) AS total_amount,
                ie.commission,
                SUM(tb.amount) * (ie.commission / 100) AS commission_amount
            FROM 
                idil_transaction_booking tb
            INNER JOIN 
                pos_order po ON tb.order_number = po.name
            INNER JOIN 
                idil_employee ie ON ie.id = po.employee_id
            WHERE 
                {where_clause}
            GROUP BY 
                po.cashier, ie.commission;
        """
        self.env.cr.execute(query, tuple(params))
        results = self.env.cr.fetchall()

        # Process results into a readable format
        report_data = []
        for row in results:
            report_data.append({
                'cashier': row[0],
                'total_amount': row[1],
                'commission_percentage': row[2],
                'commission_amount': row[3],
            })

        if export_type == "excel":
            # Generate Excel file
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet("Commission Report")

            # Write headers
            headers = ['Cashier', 'Total Amount', 'Commission (%)', 'Commission Amount']
            for col_num, header in enumerate(headers):
                worksheet.write(0, col_num, header)

            # Write data rows
            for row_num, record in enumerate(report_data, start=1):
                worksheet.write(row_num, 0, record['cashier'])
                worksheet.write(row_num, 1, record['total_amount'])
                worksheet.write(row_num, 2, record['commission_percentage'])
                worksheet.write(row_num, 3, record['commission_amount'])

            workbook.close()
            output.seek(0)

            # Create and return attachment
            attachment = self.env['ir.attachment'].create({
                'name': 'Commission_Report.xlsx',
                'type': 'binary',
                'datas': base64.b64encode(output.read()),
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            })
            output.close()

            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % attachment.id,
                'target': 'new',
            }

        return report_data

    def generate_report_pdf(self, start_date, end_date, cashier_id=None, export_type="pdf"):
        _logger.info("Starting report generation...")
        where_clauses = ["tb.trx_date BETWEEN %s AND %s"]
        params = [start_date, end_date]

        if cashier_id:
            where_clauses.append("po.cashier = %s")
            params.append(cashier_id)

        where_clause = " AND ".join(where_clauses)

        query = f"""
            SELECT 
                po.cashier, 
                SUM(tb.amount) AS total_amount,
                ie.commission,
                SUM(tb.amount) * (ie.commission / 100) AS commission_amount
            FROM 
                idil_transaction_booking tb
            INNER JOIN 
                pos_order po ON tb.order_number = po.name
            INNER JOIN 
                idil_employee ie ON ie.id = po.employee_id
            WHERE 
                {where_clause}
            GROUP BY 
                po.cashier, ie.commission;
        """
        _logger.info(f"Executing query: {query} with params: {params}")
        self.env.cr.execute(query, tuple(params))
        results = self.env.cr.fetchall()
        _logger.info(f"Query results: {results}")

        report_data = [
            {
                'cashier': row[0],
                'total_amount': row[1],
                'commission_percentage': row[2],
                'commission_amount': row[3],
            } for row in results
        ]

        if export_type == "pdf":
            _logger.info("Generating PDF...")
            output = io.BytesIO()
            doc = SimpleDocTemplate(output, pagesize=landscape(letter))
            elements = []

            styles = getSampleStyleSheet()
            title = Paragraph("<b>Commission Report</b>", styles['Title'])
            elements.append(title)
            elements.append(Spacer(1, 12))

            subtitle = Paragraph(
                f"<b>Start Date:</b> {start_date.strftime('%m/%d/%Y')} &nbsp;&nbsp;&nbsp; "
                f"<b>End Date:</b> {end_date.strftime('%m/%d/%Y')}", styles['Normal']
            )
            elements.append(subtitle)
            elements.append(Spacer(1, 12))

            if cashier_id:
                cashier_name = self.env['res.users'].browse(cashier_id).name
                cashier_info = Paragraph(f"<b>Cashier:</b> {cashier_name}", styles['Normal'])
                elements.append(cashier_info)
                elements.append(Spacer(1, 12))

            data = [['Cashier', 'Total Amount', 'Commission (%)', 'Commission Amount']]
            for record in report_data:
                data.append([
                    record['cashier'],
                    f"${record['total_amount']:,.2f}",
                    f"{record['commission_percentage']:.2f}%",
                    f"${record['commission_amount']:,.2f}",
                ])

            total_amount = sum(r['total_amount'] for r in report_data if 'total_amount' in r)
            total_commission = sum(r['commission_amount'] for r in report_data if 'commission_amount' in r)
            data.append(["Total", f"${total_amount:,.2f}", "", f"${total_commission:,.2f}"])

            table = Table(data, colWidths=[150, 150, 150, 150])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(table)

            current_datetime = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            footer = Paragraph(f"<b>Generated by:</b> {self.env.user.name} | <b>Date:</b> {current_datetime}",
                               styles['Normal'])
            elements.append(Spacer(1, 12))
            elements.append(footer)

            try:
                doc.build(elements)
            except Exception as e:
                _logger.error(f"Error building PDF: {e}")
                raise

            output.seek(0)
            attachment = self.env['ir.attachment'].create({
                'name': 'Commission_Report.pdf',
                'type': 'binary',
                'datas': base64.b64encode(output.read()),
                'mimetype': 'application/pdf',
            })
            output.close()
            _logger.info(f"PDF successfully generated: Attachment ID {attachment.id}")

            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % attachment.id,
                'target': 'new',
            }

        return report_data
