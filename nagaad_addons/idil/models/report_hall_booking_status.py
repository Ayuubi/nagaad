import io
import base64
import logging
from datetime import timedelta

from odoo import models, fields, api
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

_logger = logging.getLogger(__name__)  # Ensure logger is properly initialized


class HallBookingStatusReport(models.TransientModel):
    _name = 'idil.hall.booking.status.report'
    _description = 'Hall Booking Status Report Wizard'

    def generate_pdf_report(self):
        """Generate a PDF Report for Hall Booking Status"""

        # 🏢 Fetch Company Details
        company = self.env.company
        company_logo = company.logo if company.logo else None
        company_name = company.name or "Your Company"
        company_address = f"{company.partner_id.city or ''}, {company.partner_id.country_id.name or ''}"
        company_phone = company.partner_id.phone or "N/A"
        company_email = company.partner_id.email or "N/A"
        company_website = company.website or "N/A"

        # 📄 Create PDF document in landscape format
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),  # Landscape format
            rightMargin=30,
            leftMargin=30,
            topMargin=40,
            bottomMargin=30,
        )
        elements = []

        # 📌 Styles
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

            name='Header',
            parent=styles['Title'],
            fontSize=18,
            alignment=1  # Center aligned
        )

        # 📌 Add Company Logo (if available)
        if company_logo:
            logo_image = Image(io.BytesIO(base64.b64decode(company_logo)), width=120, height=60)
            elements.append(logo_image)
        else:
            elements.append(Paragraph("<b>No Logo Available</b>", header_style))

        elements.append(Spacer(1, 12))

        # 📌 Add Company Details
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
            f"<b>Hall Booking Status Dashboard</b>  ",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # 📌 Table Header
        data = [["Start Date", "VIP Hoos", "DHEEMAN HALL", "VIP KOR", "DHAMEYS HALL"]]

        # 🛠 Execute Query
        transaction_query = """          
            SELECT 
                DATE(hb.start_time) AS Start_date,
                COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'VIP Hoos'), '') AS VIP_Hoos,
                COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'DHEEMAN HALL'), '') AS DHEEMAN_HALL,
                COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'VIP KOR'), '') AS VIP_KOR,
                COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'DHAMEYS HALL'), '') AS DHAMEYS_HALL
            FROM public.idil_hall_booking hb
            INNER JOIN public.idil_hall h ON h.id = hb.hall_id
            WHERE hb.status IN ('booked', 'confirmed', 'draft')
            GROUP BY hb.start_time
            ORDER BY hb.start_time asc;
        """

        self.env.cr.execute(transaction_query)
        transactions = self.env.cr.fetchall()

        # ✅ Add Query Data to Table
        for transaction in transactions:
            start_date = transaction[0] or ""  # Extract Start Date
            vip_hoos = transaction[1] or ""  # VIP Hoos Booking
            dheeman_hall = transaction[2] or ""  # Dheeman Hall Booking
            vip_kor = transaction[3] or ""  # VIP Kor Booking
            dhameys_hall = transaction[4] or ""  # Dhameys Hall Booking

            # Append row data
            data.append([start_date, vip_hoos, dheeman_hall, vip_kor, dhameys_hall])

        # 📌 Apply Table Styling
        table = Table(data, colWidths=[120, 150, 150, 150, 150])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Golden brown for header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # White text for header
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align text
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold for header
            ('FONTSIZE', (0, 0), (-1, 0), 12),  # Increase header font size
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9D9D9")),  # Light grey for total row
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),  # Black text for total row
        ]))

        elements.append(Spacer(1, 20))
        elements.append(table)

        # 📌 Build and Save PDF
        doc.build(elements)

        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        # 📄 Save PDF as Attachment
        attachment = self.env['ir.attachment'].create({
            'name': 'Hall_Booking_Status.pdf',
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
        company = self.env.company
        company_logo = company.logo if company.logo else None
        company_name = company.name or "Your Company"
        company_address = f"{company.partner_id.city or ''}, {company.partner_id.country_id.name or ''}"
        company_phone = company.partner_id.phone or "N/A"
        company_email = company.partner_id.email or "N/A"
        company_website = company.website or "N/A"

        # 📄 Create PDF document in landscape format
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),  # Landscape format
            rightMargin=30,
            leftMargin=30,
            topMargin=40,
            bottomMargin=30,
        )
        elements = []

        # 📌 Styles
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

            name='Header',
            parent=styles['Title'],
            fontSize=18,
            alignment=1  # Center aligned
        )

        # 📌 Add Company Logo (if available)
        if company_logo:
            logo_image = Image(io.BytesIO(base64.b64decode(company_logo)), width=120, height=60)
            elements.append(logo_image)
        else:
            elements.append(Paragraph("<b>No Logo Available</b>", header_style))

        elements.append(Spacer(1, 12))

        # 📌 Add Company Details
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
            f"<b>Hall Booking Status Dashboard</b>  ",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # 📌 Table Header
        data = [["Start Date", "VIP Hoos", "DHEEMAN HALL", "VIP KOR", "DHAMEYS HALL"]]

        # 🛠 Execute Query
        transaction_query = """          
                    SELECT 
                        DATE(hb.start_time) AS Start_date,
                        COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'VIP Hoos'), '') AS VIP_Hoos,
                        COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'DHEEMAN HALL'), '') AS DHEEMAN_HALL,
                        COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'VIP KOR'), '') AS VIP_KOR,
                        COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'DHAMEYS HALL'), '') AS DHAMEYS_HALL
                    FROM public.idil_hall_booking hb
                    INNER JOIN public.idil_hall h ON h.id = hb.hall_id
                    WHERE hb.status IN ('booked', 'confirmed', 'draft')
                    GROUP BY hb.start_time
                    ORDER BY hb.start_time asc;
                """

        self.env.cr.execute(transaction_query)
        transactions = self.env.cr.fetchall()

        # ✅ Add Query Data to Table
        for transaction in transactions:
            start_date = transaction[0] or ""  # Extract Start Date
            vip_hoos = transaction[1] or ""  # VIP Hoos Booking
            dheeman_hall = transaction[2] or ""  # Dheeman Hall Booking
            vip_kor = transaction[3] or ""  # VIP Kor Booking
            dhameys_hall = transaction[4] or ""  # Dhameys Hall Booking

            # Append row data
            data.append([start_date, vip_hoos, dheeman_hall, vip_kor, dhameys_hall])

        # 📌 Apply Table Styling
        table = Table(data, colWidths=[120, 150, 150, 150, 150])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Golden brown for header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # White text for header
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align text
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold for header
            ('FONTSIZE', (0, 0), (-1, 0), 12),  # Increase header font size
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9D9D9")),  # Light grey for total row
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),  # Black text for total row
        ]))

        elements.append(Spacer(1, 20))
        elements.append(table)

        # 📌 Build and Save PDF
        doc.build(elements)

        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Hall_Hall_Status_Report.pdf',
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
                'subject': 'Hall Booking Status Dashboard',
                'body_html': f'''
                    <p>Dear {recipient_name},</p>
                    <p>Please find attached the Hall Booking Status Dashboard.</p>
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

    def send_hall_booking_status_by_email_cron(self):
        """Generate and send the hall summary report via cron job"""

        company = self.env.company
        company_logo = company.logo if company.logo else None
        company_name = company.name or "Your Company"
        company_address = f"{company.partner_id.city or ''}, {company.partner_id.country_id.name or ''}"
        company_phone = company.partner_id.phone or "N/A"
        company_email = company.partner_id.email or "N/A"
        company_website = company.website or "N/A"

        # 📄 Create PDF document in landscape format
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),  # Landscape format
            rightMargin=30,
            leftMargin=30,
            topMargin=40,
            bottomMargin=30,
        )
        elements = []

        # 📌 Styles
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

            name='Header',
            parent=styles['Title'],
            fontSize=18,
            alignment=1  # Center aligned
        )

        # 📌 Add Company Logo (if available)
        if company_logo:
            logo_image = Image(io.BytesIO(base64.b64decode(company_logo)), width=120, height=60)
            elements.append(logo_image)
        else:
            elements.append(Paragraph("<b>No Logo Available</b>", header_style))

        elements.append(Spacer(1, 12))

        # 📌 Add Company Details
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
            f"<b>Hall Booking Status Dashboard</b>  ",
            left_align_style
        )
        elements.append(date_range)
        elements.append(Spacer(1, 12))

        # 📌 Table Header
        data = [["Start Date", "VIP Hoos", "DHEEMAN HALL", "VIP KOR", "DHAMEYS HALL"]]

        # 🛠 Execute Query
        transaction_query = """          
                            SELECT 
                                DATE(hb.start_time) AS Start_date,
                                COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'VIP Hoos'), '') AS VIP_Hoos,
                                COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'DHEEMAN HALL'), '') AS DHEEMAN_HALL,
                                COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'VIP KOR'), '') AS VIP_KOR,
                                COALESCE(MAX(hb.status || ' - Due $' || ROUND(hb.remaining_amount::NUMERIC, 2)) FILTER (WHERE h.name = 'DHAMEYS HALL'), '') AS DHAMEYS_HALL
                            FROM public.idil_hall_booking hb
                            INNER JOIN public.idil_hall h ON h.id = hb.hall_id
                            WHERE hb.status IN ('booked', 'confirmed', 'draft')
                            GROUP BY hb.start_time
                            ORDER BY hb.start_time asc;
                        """

        self.env.cr.execute(transaction_query)
        transactions = self.env.cr.fetchall()

        # ✅ Add Query Data to Table
        for transaction in transactions:
            start_date = transaction[0] or ""  # Extract Start Date
            vip_hoos = transaction[1] or ""  # VIP Hoos Booking
            dheeman_hall = transaction[2] or ""  # Dheeman Hall Booking
            vip_kor = transaction[3] or ""  # VIP Kor Booking
            dhameys_hall = transaction[4] or ""  # Dhameys Hall Booking

            # Append row data
            data.append([start_date, vip_hoos, dheeman_hall, vip_kor, dhameys_hall])

        # 📌 Apply Table Styling
        table = Table(data, colWidths=[120, 150, 150, 150, 150])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#B6862D")),  # Golden brown for header
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),  # White text for header
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Grid styling
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center align text
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Bold for header
            ('FONTSIZE', (0, 0), (-1, 0), 12),  # Increase header font size
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#D9D9D9")),  # Light grey for total row
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),  # Black text for total row
        ]))

        elements.append(Spacer(1, 20))
        elements.append(table)

        # 📌 Build and Save PDF
        doc.build(elements)

        buffer.seek(0)
        pdf_data = buffer.read()
        buffer.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'Hall_Hall_Status_Report.pdf',
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
                'subject': 'Hall Booking Status Dashboard',
                'body_html': f'''
                    <p>Dear {recipient.name},</p>
                    <p>Please find attached the Hall Booking Status Dashboard.</p>
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
