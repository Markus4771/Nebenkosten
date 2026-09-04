import smtplib
from email.message import EmailMessage

def send_email(settings, recipient, subject, body, attachment=None, attachment_name=None):
    host=(settings.get('smtp_host') or '').strip()
    if not host: raise ValueError('SMTP-Server ist nicht konfiguriert.')
    port=int(settings.get('smtp_port') or 587); security=(settings.get('smtp_security') or 'starttls').lower()
    sender=(settings.get('smtp_from') or settings.get('smtp_user') or '').strip()
    if not sender: raise ValueError('Absenderadresse fehlt.')
    msg=EmailMessage(); msg['From']=sender; msg['To']=recipient; msg['Subject']=subject; msg.set_content(body)
    if attachment is not None: msg.add_attachment(attachment,maintype='application',subtype='pdf',filename=attachment_name or 'Nebenkostenabrechnung.pdf')
    cls=smtplib.SMTP_SSL if security=='ssl' else smtplib.SMTP
    with cls(host,port,timeout=15) as smtp:
        if security=='starttls': smtp.starttls()
        if settings.get('smtp_user'): smtp.login(settings['smtp_user'],settings.get('smtp_password') or '')
        smtp.send_message(msg)
