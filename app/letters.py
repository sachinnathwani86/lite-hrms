"""
PDF generation for HR lifecycle letters: offer, appointment, termination,
relieving. Standard boilerplate wording with merge fields that can be
replaced for a deployment's legal wording.
"""
import os
import calendar
from io import BytesIO
from decimal import Decimal
from datetime import date
from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from app.payroll import (
    calculate_salary_breakup, financial_year_breakup, EARNING_COMPONENTS, DEDUCTION_COMPONENTS
)

_styles = getSampleStyleSheet()
_body = ParagraphStyle("Body", parent=_styles["Normal"], alignment=TA_JUSTIFY, spaceAfter=12, leading=16)
_title = ParagraphStyle("LetterTitle", parent=_styles["Heading1"], spaceAfter=18)

_MUTED = colors.HexColor("#6b7280")
_BORDER = colors.HexColor("#e3e7ee")
_TEXT = colors.HexColor("#1a2233")
_GREEN_BG = colors.HexColor("#e6f4ea")
_GREEN = colors.HexColor("#1e7e34")

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digit_words(n):
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_digit_words(n):
    if n >= 100:
        rest = n % 100
        return _ONES[n // 100] + " Hundred" + (" " + _two_digit_words(rest) if rest else "")
    return _two_digit_words(n)


def _number_to_words(n):
    """Integer to words using the Indian numbering system (crore/lakh/thousand)."""
    if n == 0:
        return "Zero"
    parts = []
    crore, n = divmod(n, 10000000)
    lakh, n = divmod(n, 100000)
    thousand, n = divmod(n, 1000)
    hundred = n
    if crore:
        parts.append(_three_digit_words(crore) + " Crore")
    if lakh:
        parts.append(_two_digit_words(lakh) + " Lakh")
    if thousand:
        parts.append(_two_digit_words(thousand) + " Thousand")
    if hundred:
        parts.append(_three_digit_words(hundred))
    return " ".join(parts)


def _amount_in_words(amount):
    amount = Decimal(amount).quantize(Decimal("0.01"))
    rupees, paise = int(amount), int((amount - int(amount)) * 100)
    words = f"Indian Rupee {_number_to_words(rupees)} Only"
    if paise:
        words = f"Indian Rupee {_number_to_words(rupees)} and {_number_to_words(paise)} Paise Only"
    return words


def _letterhead_path(company):
    if not company.letterhead_filename:
        return None
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], "letterheads", company.letterhead_filename)
    return path if os.path.exists(path) else None


def _render(company_name, title, date_str, paragraphs, extra_flowables=None, letterhead_path=None):
    buf = BytesIO()
    # ponytail: fixed 2in top margin clears a typical pre-printed header; adjust if a
    # company's letterhead has a taller/shorter header band.
    top_margin = 2 * inch if letterhead_path else 1 * inch
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=top_margin, bottomMargin=1 * inch)
    story = []
    if not letterhead_path:
        story.append(Paragraph(company_name, _styles["Heading2"]))
        story.append(Spacer(1, 6))
    story.append(Paragraph(date_str, _styles["Normal"]))
    story.append(Spacer(1, 18))
    story.append(Paragraph(title, _title))
    for p in paragraphs:
        story.append(Paragraph(p, _body))
    if extra_flowables:
        story.extend(extra_flowables)

    def _draw_letterhead(c, _doc):
        c.drawImage(letterhead_path, 0, 0, width=A4[0], height=A4[1], preserveAspectRatio=False, mask="auto")

    if letterhead_path:
        doc.build(story, onFirstPage=_draw_letterhead, onLaterPages=_draw_letterhead)
    else:
        doc.build(story)
    buf.seek(0)
    return buf


def _ctc_breakup_table(monthly_gross):
    """CTC breakup table for a monthly gross, or None if it can't be split (e.g. gross too low)."""
    if not monthly_gross:
        return None
    try:
        breakup = calculate_salary_breakup(monthly_gross)
    except ValueError:
        return None

    gross = sum(breakup[n] for n in EARNING_COMPONENTS)
    deductions = sum(breakup[n] for n in DEDUCTION_COMPONENTS)
    net = gross - deductions

    rows = [["Component", "Monthly (Rs.)", "Annual (Rs.)"]]
    for name in EARNING_COMPONENTS:
        rows.append([name, f"{breakup[name]:,.2f}", f"{breakup[name] * 12:,.2f}"])
    rows.append(["Gross Salary", f"{gross:,.2f}", f"{gross * 12:,.2f}"])
    for name in DEDUCTION_COMPONENTS:
        rows.append([f"Less: {name}", f"({breakup[name]:,.2f})", f"({breakup[name] * 12:,.2f})"])
    rows.append(["Net Take-Home (CTC)", f"{net:,.2f}", f"{net * 12:,.2f}"])

    table = Table(rows, colWidths=[220, 130, 130], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16233d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, len(EARNING_COMPONENTS) + 1), (-1, len(EARNING_COMPONENTS) + 1), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e3e7ee")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def offer_letter(candidate):
    designation = candidate.designation.title if candidate.designation else "the offered role"
    paragraphs = [
        f"Dear {candidate.full_name},",
        f"We are pleased to offer you the position of <b>{designation}</b> at "
        f"{candidate.company.name}. This letter confirms our offer of employment, "
        f"subject to the terms discussed and any documentation we may request.",
        f"Your proposed monthly gross compensation will be <b>Rs. {candidate.proposed_salary}</b>, "
        f"payable per the company's standard payroll cycle. A detailed CTC breakup is "
        f"enclosed below.",
        "Please confirm your acceptance of this offer by replying to this letter. "
        "A formal appointment letter with detailed terms of employment will follow "
        "once you join.",
        "We look forward to having you on the team.",
        "Sincerely,<br/>HR Department",
    ]
    extra = []
    table = _ctc_breakup_table(candidate.proposed_salary)
    if table:
        extra = [PageBreak(), Paragraph("CTC Breakup", _styles["Heading3"]), Spacer(1, 6), table]
    return _render(
        candidate.company.name, "Offer Letter",
        f"Date: {candidate.offer_date}", paragraphs,
        extra_flowables=extra,
        letterhead_path=_letterhead_path(candidate.company)
    )


def appointment_letter(employee):
    designation = employee.designation.title if employee.designation else "your role"
    paragraphs = [
        f"Dear {employee.full_name},",
        f"Further to your acceptance of our offer, we are pleased to confirm your "
        f"appointment as <b>{designation}</b> at {employee.company.name}, effective "
        f"<b>{employee.date_of_joining}</b>.",
        f"Your monthly gross compensation will be <b>Rs. {employee.monthly_gross}</b>, "
        f"subject to applicable statutory deductions, payable per the company's "
        f"standard payroll cycle. A detailed CTC breakup is enclosed below.",
        "Your employment will be governed by the company's policies as amended "
        "from time to time. This letter, along with your offer letter, constitutes "
        "your terms of appointment.",
        "We welcome you to the team and wish you a successful career with us.",
        "Sincerely,<br/>HR Department",
    ]
    extra = []
    table = _ctc_breakup_table(employee.monthly_gross)
    if table:
        extra = [PageBreak(), Paragraph("CTC Breakup", _styles["Heading3"]), Spacer(1, 6), table]
    return _render(
        employee.company.name, "Appointment Letter",
        f"Date: {date.today()}", paragraphs,
        extra_flowables=extra,
        letterhead_path=_letterhead_path(employee.company)
    )


def termination_letter(employee):
    designation = employee.designation.title if employee.designation else "your role"
    reason = employee.termination_reason or "as discussed"
    paragraphs = [
        f"Dear {employee.full_name},",
        f"This letter is to inform you that your employment with {employee.company.name} "
        f"as <b>{designation}</b> is being terminated, {reason}.",
        f"Your last working day with the company will be <b>{employee.relieving_date}</b>. "
        f"All dues, if any, will be settled as per company policy following completion "
        f"of the exit formalities.",
        "Please ensure the return of any company property in your possession and "
        "complete the handover of pending work prior to your last working day.",
        "Sincerely,<br/>HR Department",
    ]
    return _render(
        employee.company.name, "Termination Letter",
        f"Date: {date.today()}", paragraphs,
        letterhead_path=_letterhead_path(employee.company)
    )


def relieving_letter(employee):
    designation = employee.designation.title if employee.designation else "your role"
    paragraphs = [
        f"Dear {employee.full_name},",
        f"This is to confirm that you were employed with {employee.company.name} as "
        f"<b>{designation}</b> from <b>{employee.date_of_joining}</b> to "
        f"<b>{employee.relieving_date}</b>.",
        "You have been relieved of your duties with effect from the above date. "
        "We confirm that all dues and formalities pertaining to your separation "
        "have been settled as per company records.",
        "We wish you the very best in your future endeavours.",
        "Sincerely,<br/>HR Department",
    ]
    return _render(
        employee.company.name, "Relieving Letter",
        f"Date: {date.today()}", paragraphs,
        letterhead_path=_letterhead_path(employee.company)
    )


def _payslip_header(company_name, month_name, year):
    name_style = ParagraphStyle("PsCompany", parent=_styles["Heading1"], fontSize=18, leading=22)
    label_style = ParagraphStyle("PsLabel", parent=_styles["Normal"], alignment=TA_RIGHT, textColor=_MUTED, fontSize=9.5)
    month_style = ParagraphStyle("PsMonth", parent=_styles["Normal"], alignment=TA_RIGHT, fontName="Helvetica-Bold", fontSize=13)

    left = [Paragraph(company_name, name_style)]
    right = [Paragraph("Payslip For the Month", label_style), Paragraph(f"{month_name} {year}", month_style)]

    t = Table([[left, right]], colWidths=[280, 171])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -1), 0.75, _BORDER),
    ]))
    return t


def _payslip_summary_and_net(rows, net_pay, paid_days, lop_days):
    label_style = ParagraphStyle("SumLabel", parent=_styles["Normal"], fontSize=9.5, textColor=_MUTED)
    value_style = ParagraphStyle("SumValue", parent=_styles["Normal"], fontSize=9.5, fontName="Helvetica-Bold")
    summary_data = [[Paragraph(label, label_style), Paragraph(":", label_style), Paragraph(str(value), value_style)]
                     for label, value in rows]
    summary = Table(summary_data, colWidths=[115, 8, 157])
    summary.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))

    amt_style = ParagraphStyle("NetAmt", parent=_styles["Normal"], fontSize=19, fontName="Helvetica-Bold", textColor=_TEXT, leading=24)
    net_label_style = ParagraphStyle("NetLabel", parent=_styles["Normal"], fontSize=9, textColor=_MUTED)
    top = Table([[Paragraph(f"Rs. {net_pay:,.2f}", amt_style)], [Paragraph("Employee Net Pay", net_label_style)]], colWidths=[171])
    top.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _GREEN_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3, _GREEN),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 12),
        ("BOTTOMPADDING", (0, 0), (0, 0), 4),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 12),
    ]))

    days_style = ParagraphStyle("DaysLabel", parent=_styles["Normal"], fontSize=9, textColor=_MUTED)
    days_val_style = ParagraphStyle("DaysVal", parent=_styles["Normal"], fontSize=9, fontName="Helvetica-Bold", alignment=TA_RIGHT)
    bottom = Table([
        [Paragraph("Paid Days", days_style), Paragraph(str(paid_days), days_val_style)],
        [Paragraph("LOP Days", days_style), Paragraph(str(lop_days), days_val_style)],
    ], colWidths=[110, 61])
    bottom.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    box = Table([[top], [bottom]], colWidths=[171])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, _BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    t = Table([[summary, box]], colWidths=[280, 171])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LINEBELOW", (0, 0), (-1, -1), 0.75, _BORDER),
    ]))
    return t


def _payslip_earnings_deductions_table(earnings, deductions, gross, deductions_total, month):
    header_style = ParagraphStyle("EdHeader", parent=_styles["Normal"], fontSize=9, fontName="Helvetica-Bold", textColor=_MUTED)
    rows = [[Paragraph(h, header_style) for h in ["EARNINGS", "AMOUNT", "YTD", "DEDUCTIONS", "AMOUNT", "YTD"]]]
    earning_items = list(earnings.items()) or [("Basic", gross)]
    deduction_items = list(deductions.items())
    for i in range(max(len(earning_items), len(deduction_items))):
        e_name, e_amt = earning_items[i] if i < len(earning_items) else ("", None)
        d_name, d_amt = deduction_items[i] if i < len(deduction_items) else ("", None)
        # ponytail: YTD = this month's component amount x month-of-year, since
        # historical payroll runs aren't stored per-component. Accurate as long
        # as the salary structure hasn't changed and no LWP applied mid-year.
        rows.append([
            e_name, f"{e_amt:,.2f}" if e_amt is not None else "", f"{e_amt * month:,.2f}" if e_amt is not None else "",
            d_name, f"{d_amt:,.2f}" if d_amt is not None else "", f"{d_amt * month:,.2f}" if d_amt is not None else "",
        ])
    rows.append(["Gross Earnings", f"{gross:,.2f}", "", "Total Deductions", f"{deductions_total:,.2f}", ""])

    table = Table(rows, colWidths=[95, 65, 65, 95, 65, 65], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (2, -1), "RIGHT"),
        ("ALIGN", (4, 0), (5, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, _BORDER),
        ("LINEABOVE", (0, -1), (-1, -1), 0.75, _BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _payslip_net_bar(net_pay):
    title_style = ParagraphStyle("BarTitle", parent=_styles["Normal"], fontSize=10, fontName="Helvetica-Bold")
    sub_style = ParagraphStyle("BarSub", parent=_styles["Normal"], fontSize=8.5, textColor=_MUTED)
    amt_style = ParagraphStyle("BarAmt", parent=_styles["Normal"], fontSize=15, fontName="Helvetica-Bold", alignment=TA_RIGHT)

    left = [Paragraph("TOTAL NET PAYABLE", title_style), Paragraph("Gross Earnings - Total Deductions", sub_style)]
    t = Table([[left, Paragraph(f"Rs. {net_pay:,.2f}", amt_style)]], colWidths=[300, 151])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, _BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f6f9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def payslip(employee, month, year, earnings, deductions, gross, deductions_total, net_pay, lop_days=0):
    """Monthly payslip PDF. earnings/deductions are {component_name: Decimal amount}."""
    designation = employee.designation.title if employee.designation else ""
    month_name = calendar.month_name[month]
    paid_days = calendar.monthrange(year, month)[1]
    pay_date = date(year, month, paid_days)

    summary_rows = [
        ("Employee Name", employee.full_name),
        ("Designation", designation or "-"),
        ("Employee ID", f"EMP{employee.id:04d}"),
        ("Date of Joining", employee.date_of_joining.strftime("%d/%m/%Y") if employee.date_of_joining else "-"),
        ("Pay Period", f"{month_name} {year}"),
        ("Pay Date", pay_date.strftime("%d/%m/%Y")),
    ]

    story = [
        _payslip_header(employee.company.name, month_name, year),
        Spacer(1, 14),
        # ponytail: LOP Days fixed at 0 — no attendance/LWP data exists yet
        # (see calculate_lwp_deduction in app/payroll.py, not wired in).
        _payslip_summary_and_net(summary_rows, net_pay, paid_days, lop_days),
        Spacer(1, 14),
        _payslip_earnings_deductions_table(earnings, deductions, gross, deductions_total, month),
        Spacer(1, 16),
        _payslip_net_bar(net_pay),
        Spacer(1, 10),
        Paragraph(f"Amount In Words: {_amount_in_words(net_pay)}", ParagraphStyle(
            "Words", parent=_styles["Normal"], fontSize=9, alignment=TA_RIGHT
        )),
        Spacer(1, 24),
        Paragraph(
            f"This document has been automatically generated by {employee.company.name}'s HR system; "
            "therefore, a signature is not required.",
            ParagraphStyle("Footer", parent=_styles["Normal"], fontSize=8, textColor=_MUTED, alignment=1)
        ),
    ]

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1 * inch, bottomMargin=1 * inch)
    doc.build(story)
    buf.seek(0)
    return buf


def fy_breakup_letter(employee, fy_start_year):
    """Component-wise salary breakup for an Indian financial year (Apr-Mar)."""
    earnings, deductions = financial_year_breakup(employee, fy_start_year)
    gross = sum(earnings.values())
    deductions_total = sum(deductions.values())
    net = gross - deductions_total
    fy_label = f"FY {fy_start_year}-{str(fy_start_year + 1)[-2:]}"

    paragraphs = [
        f"Component-wise salary breakup for <b>{employee.full_name}</b> for "
        f"<b>{fy_label}</b> (April {fy_start_year} to March {fy_start_year + 1}).",
    ]

    rows = [["Component", "Amount (Rs.)"]]
    for name, amount in earnings.items():
        rows.append([name, f"{amount:,.2f}"])
    rows.append(["Gross Salary", f"{gross:,.2f}"])
    for name, amount in deductions.items():
        rows.append([f"Less: {name}", f"({amount:,.2f})"])
    rows.append(["Net Take-Home", f"{net:,.2f}"])

    table = Table(rows, colWidths=[280, 171], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16233d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, len(earnings) + 1), (-1, len(earnings) + 1), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    return _render(
        employee.company.name, f"Salary Breakup — {fy_label}",
        f"Date: {date.today()}", paragraphs,
        extra_flowables=[Spacer(1, 12), table],
        letterhead_path=_letterhead_path(employee.company)
    )
