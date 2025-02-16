import logging

from odoo import models, fields, api
import xlsxwriter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
import base64
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)  # Ensure logger is properly initialized


class Kitchen_ReportWizard(models.TransientModel):
    _name = 'idil.hall.summary.report'
    _description = 'Hall Summary Report Wizard'

    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)

    def generate_pdf_report(self):
        company = self.env.company  # Fetch the active company
        company_logo = company.logo if company.logo else None
        company_name = company.name or "Your Company"
        company_address = f"{company.partner_id.city or ''}, {company.partner_id.country_id.name or ''}"
        company_phone = company.partner_id.phone or "N/A"
        company_email = company.partner_id.email or "N/A"
        company_website = company.website or "N/A"

        # Create PDF document in landscape format
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),  # Set landscape format
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
            logo_image = Image(io.BytesIO(base64.b64decode(company_logo)), width=120, height=60)
            elements.append(logo_image)
        else:
            elements.append(Paragraph("<b>No Logo Available</b>", header_style))

        elements.append(Spacer(1, 12))

        # Add company details
        company_name_paragraph = Paragraph(f"<b>{company_name.upper()}</b>", header_style)
        company_details_paragraph = Paragraph(
            f"{company_address}<br/>"
            f"Phone No.: {company_phone}<br/>"
            f"Email: {company_email}<br/>"
            f"Web: {company_website}",
            subtitle_style
        )
        elements.extend([company_name_paragraph, Spacer(1, 6), company_details_paragraph, Spacer(1, 20)])

        # Add Date Range
        date_range = Paragraph(
            f"<b>Date from:</b> {self.start_date.strftime('%d/%m/%Y')}<br/>"
            f"<b>Date to:</b> {self.end_date.strftime('%d/%m/%Y')}<br/>",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # Table Header
        data = [["Hall Name", "# Guests", "Avg Cost", "Total Amount", "Paid Amount", "Due Amount", "Service Amount"]]

        # Execute Query
        transaction_query = """          
            SELECT  h.name, 
                    sum(hb.no_of_guest) as no_of_guest, 
                    avg(hb.price_per_guest) as price_per_guest_AVG, 
                    sum(hb.total_price) as total_price, 
                    sum(hb.amount_paid) as amount_paid,
                    sum(hb.remaining_amount) as remaining_amount, 
                    sum(hb.extra_service_amount) as extra_service_amount
            FROM public.idil_hall h
            INNER JOIN public.idil_hall_booking hb 
            ON h.id = hb.hall_id
            WHERE hb.booking_date BETWEEN %s AND %s
            GROUP BY h.name;
        """

        self.env.cr.execute(transaction_query, (self.start_date, self.end_date))
        transactions = self.env.cr.fetchall()

        # Initialize grand totals
        grand_total_guests = 0
        grand_total_avg_cost = 0
        grand_total_amount = 0
        grand_total_paid = 0
        grand_total_due = 0
        grand_total_service = 0

        for transaction in transactions:
            hall_name = transaction[0] or ""
            no_of_guests = transaction[1] or 0
            avg_cost = transaction[2] or 0
            total_amount = transaction[3] or 0
            paid_amount = transaction[4] or 0
            due_amount = transaction[5] or 0
            service_amount = transaction[6] or 0

            # Accumulate grand totals
            grand_total_guests += no_of_guests
            grand_total_avg_cost += avg_cost
            grand_total_amount += total_amount
            grand_total_paid += paid_amount
            grand_total_due += due_amount
            grand_total_service += service_amount

            # Append data row
            data.append([
                hall_name,
                f"{no_of_guests:,}",
                f"${avg_cost:,.2f}",
                f"${total_amount:,.2f}",
                f"${paid_amount:,.2f}",
                f"${due_amount:,.2f}",
                f"${service_amount:,.2f}",
            ])

        # Append Grand Total row
        data.append([
            "Grand Total",
            f"{grand_total_guests:,}",
            f"${grand_total_avg_cost:,.2f}",
            f"${grand_total_amount:,.2f}",
            f"${grand_total_paid:,.2f}",
            f"${grand_total_due:,.2f}",
            f"${grand_total_service:,.2f}",
        ])

        # Apply table styling
        table = Table(data, colWidths=[200, 80, 80, 100, 100, 80, 90])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Golden brown for header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # White text for header
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align text
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold for header
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Grand Total in bold
            ('FONTSIZE', (0, -1), (-1, -1), 12),  # Grand Total larger font
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9D9D9")),  # Light grey for Grand Total row
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),  # Black text for Grand Total row
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
            'name': 'Hall_Summary_Report.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    def send_pdf_report_by_email(self):
        company = self.env.company  # Fetch the active company
        company_logo = company.logo if company.logo else None
        company_name = company.name or "Your Company"

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

        # Styles
        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            name='Header',
            parent=styles['Title'],
            fontSize=18,
            textColor=colors.HexColor("#B6862D"),
            alignment=1  # Center aligned
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

        # Add company logo
        if company_logo:
            logo_image = Image(io.BytesIO(base64.b64decode(company_logo)), width=120, height=60)
            elements.append(logo_image)
        else:
            elements.append(Paragraph("<b>No Logo Available</b>", header_style))

        elements.append(Spacer(1, 12))

        # Add company details
        company_name_paragraph = Paragraph(f"<b>{company_name.upper()}</b>", header_style)
        elements.append(company_name_paragraph)
        elements.append(Spacer(1, 20))

        # Add Date Range
        date_range = Paragraph(
            f"<b>Date from:</b> {self.start_date.strftime('%d/%m/%Y')}<br/>"
            f"<b>Date to:</b> {self.end_date.strftime('%d/%m/%Y')}<br/>",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # Table Header
        data = [["Hall Name", "# Guests", "Avg Cost", "Total Amount", "Paid Amount", "Due Amount", "Service Amount"]]

        # Execute Query
        transaction_query = """          
            SELECT  h.name, 
                    sum(hb.no_of_guest) as no_of_guest, 
                    avg(hb.price_per_guest) as price_per_guest_AVG, 
                    sum(hb.total_price) as total_price, 
                    sum(hb.amount_paid) as amount_paid,
                    sum(hb.remaining_amount) as remaining_amount, 
                    sum(hb.extra_service_amount) as extra_service_amount
            FROM public.idil_hall h
            INNER JOIN public.idil_hall_booking hb 
            ON h.id = hb.hall_id
            WHERE hb.booking_date BETWEEN %s AND %s
            GROUP BY h.name;
        """

        self.env.cr.execute(transaction_query, (self.start_date, self.end_date))
        transactions = self.env.cr.fetchall()

        # Initialize grand totals
        grand_total_guests = 0
        grand_total_avg_cost = 0
        grand_total_amount = 0
        grand_total_paid = 0
        grand_total_due = 0
        grand_total_service = 0

        for transaction in transactions:
            hall_name = transaction[0] or ""
            no_of_guests = transaction[1] or 0
            avg_cost = transaction[2] or 0
            total_amount = transaction[3] or 0
            paid_amount = transaction[4] or 0
            due_amount = transaction[5] or 0
            service_amount = transaction[6] or 0

            # Accumulate grand totals
            grand_total_guests += no_of_guests
            grand_total_avg_cost += avg_cost
            grand_total_amount += total_amount
            grand_total_paid += paid_amount
            grand_total_due += due_amount
            grand_total_service += service_amount

            # Append data row
            data.append([
                hall_name,
                f"{no_of_guests:,}",
                f"${avg_cost:,.2f}",
                f"${total_amount:,.2f}",
                f"${paid_amount:,.2f}",
                f"${due_amount:,.2f}",
                f"${service_amount:,.2f}",
            ])

        # Append Grand Total row
        data.append([
            "Grand Total",
            f"{grand_total_guests:,}",
            f"${grand_total_avg_cost:,.2f}",
            f"${grand_total_amount:,.2f}",
            f"${grand_total_paid:,.2f}",
            f"${grand_total_due:,.2f}",
            f"${grand_total_service:,.2f}",
        ])

        # Apply table styling
        table = Table(data, colWidths=[200, 80, 80, 100, 100, 80, 90])

        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9D9D9")),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),
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
            'name': 'Hall_Summary_Report.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        # Fetch recipient emails and names
        recipients = self.env['idil.email.recipient'].search([('active', '=', True)])

        if not recipients:
            return {'warning': {'title': "No Recipients", 'message': "No active recipients found in the system."}}

        static_bcc_email = "khadar1889@gmail.com"  # Hardcoded BCC email

        for recipient in recipients:
            recipient_name = recipient.name or "User"
            recipient_email = recipient.email

            # Create email message with recipient's name
            mail_values = {
                'subject': 'Hall Summary Report',
                'body_html': f'''
                    <p>Dear {recipient_name},</p>
                    <p>Please find attached the Hall Summary Report.</p>
                    <p>Best regards,<br/>{company_name}</p>
                ''',
                'email_to': recipient_email,
                'email_cc': static_bcc_email,  # Always BCC to this email
                'attachment_ids': [(4, attachment.id)],
            }

            # Send email
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()

        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Email sent successfully!',
                'type': 'rainbow_man',
            }
        }

    def send_pdf_report_by_email_cron(self):
        """Generate and send the hall summary report via cron job"""

        company = self.env.company
        company_name = company.name or "Your Company"

        # ✅ Handle missing dates for cron jobs
        start_date = fields.Date.today() - timedelta(days=7)
        end_date = fields.Date.today()

        _logger.info(f"Sending Hall Summary Report for {start_date} to {end_date}")  # Debugging line

        # Create PDF document
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

        # Styles
        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            name='Header',
            parent=styles['Title'],
            fontSize=18,
            textColor=colors.HexColor("#B6862D"),
            alignment=1
        )

        # Add company details
        elements.append(Paragraph(f"<b>{company_name.upper()}</b>", header_style))
        elements.append(Spacer(1, 20))

        # Add Date Range
        date_range = Paragraph(
            f"<b>Date from:</b> {start_date.strftime('%d/%m/%Y')}<br/>"
            f"<b>Date to:</b> {end_date.strftime('%d/%m/%Y')}<br/>",
            styles['Normal']
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # Table Header
        data = [["Hall Name", "# Guests", "Avg Cost", "Total Amount", "Paid Amount", "Due Amount", "Service Amount"]]

        # Execute Query
        transaction_query = """          
            SELECT  h.name, 
                    sum(hb.no_of_guest) as no_of_guest, 
                    avg(hb.price_per_guest) as price_per_guest_AVG, 
                    sum(hb.total_price) as total_price, 
                    sum(hb.amount_paid) as amount_paid,
                    sum(hb.remaining_amount) as remaining_amount, 
                    sum(hb.extra_service_amount) as extra_service_amount
            FROM public.idil_hall h
            INNER JOIN public.idil_hall_booking hb 
            ON h.id = hb.hall_id
            WHERE hb.booking_date BETWEEN %s AND %s
            GROUP BY h.name;
        """

        self.env.cr.execute(transaction_query, (start_date, end_date))
        transactions = self.env.cr.fetchall()

        for transaction in transactions:
            # ✅ Ensure all numeric values are not None, otherwise replace with 0.0
            hall_name = transaction[0] or "N/A"
            no_of_guests = transaction[1] or 0
            avg_cost = transaction[2] or 0.0
            total_amount = transaction[3] or 0.0
            paid_amount = transaction[4] or 0.0
            due_amount = transaction[5] or 0.0
            service_amount = transaction[6] or 0.0  # ✅ Fix: Replace None with 0.0

            data.append([
                hall_name,
                f"{no_of_guests:,}",
                f"${avg_cost:,.2f}",
                f"${total_amount:,.2f}",
                f"${paid_amount:,.2f}",
                f"${due_amount:,.2f}",
                f"${service_amount:,.2f}",
            ])

        # Apply table styling
        table = Table(data, colWidths=[200, 80, 80, 100, 100, 80, 90])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9D9D9")),
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
            'name': 'Hall_Summary_Report.pdf',
            'type': 'binary',
            'datas': base64.b64encode(pdf_data),
            'mimetype': 'application/pdf',
        })

        # Fetch recipients
        recipients = self.env['idil.email.recipient'].search([('active', '=', True)])
        static_bcc_email = "khadar1889@gmail.com"

        if not recipients:
            _logger.warning("No active recipients found, skipping email send.")
            return False

        for recipient in recipients:
            mail_values = {
                'subject': 'Hall Summary Report',
                'body_html': f'''
                    <p>Dear {recipient.name},</p>
                    <p>Please find attached the Hall Summary Report.</p>
                    <p>Best regards,<br/>{company_name}</p>
                ''',
                'email_to': recipient.email,
                'email_cc': static_bcc_email,
                'attachment_ids': [(4, attachment.id)],
            }

            mail = self.env['mail.mail'].create(mail_values)
            mail.send()
            _logger.info(f"Report sent to {recipient.email}")

        return True
