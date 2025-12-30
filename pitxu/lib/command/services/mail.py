from pyxavi import Config, Dictionary, full_stack, dd

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command
from pitxu.lib.eink import EinkCanvas

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class ServiceMail(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(ServiceMail, self).init_pyxavi(config=config, params=params)
    
    def send_email(self, subject: str, body: str) -> bool:
        '''
        Sends an email to the specified address.

        ⚠️ Starting from September 30, 2024, Google no longer supports "Less secure apps".
        This solves the issue: https://stackoverflow.com/a/76439245

        Args:
            to_address: The recipient's email address.
            subject: The subject of the email.
            body: The body of the email.

        Returns:
            True if the email was sent successfully, False otherwise.
        '''
        try:

            server = self._xconfig.get("services.mail.host")
            port = self._xconfig.get("services.mail.port")
            username = self._xparams.get("mail.user_name")
            password = self._xparams.get("mail.password")
            from_address = self._xparams.get("mail.user_address")
            to_address = self._xconfig.get("services.mail.address_to")

            debug_info = "Sending email with the following parameters:"
            debug_info += f"\n  Server: {server}"
            debug_info += f"\n  Port: {port}"
            debug_info += f"\n  Username: {username}"
            debug_info += f"\n  Password: Using App Passwords from GMail 2-step setup."
            debug_info += f"\n  From Address: {from_address}"
            debug_info += f"\n  To Address: {to_address}"
            debug_info += f"\n  Subject: {subject}"
            self._xlog.debug(debug_info)

            # msg = MIMEMultipart()
            # msg['From'] = from_address
            # msg['To'] = to_address
            # msg['Subject'] = subject

            # msg.attach(MIMEText(body, 'plain'))

            # server = smtplib.SMTP(smtp_server, smtp_port)
            # server.starttls()
            # server.login(smtp_username, smtp_password)
            # server.send_message(msg)
            # server.quit()

            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = from_address
            msg['To'] = to_address
            with smtplib.SMTP(host=server, port=port) as smtp_server:
                smtp_server.starttls()
                smtp_server.ehlo()
                smtp_server.login(username, password)
                smtp_server.sendmail(from_address, [to_address], msg.as_string())

            self._xlog.debug(f"Email sent to {to_address} with subject '{subject}'")
            return True
        except Exception as e:
            self._xlog.error(f"🛑 Error sending email to {to_address}: {e}")
            self._xlog.debug(full_stack())
            return False
    
    def callback_send_email(self, main_instance, value: any, args: dict = None) -> None:
        """
        Callback for `send_email` that gets called AFTER chatbot from `main`.

        Args:
            main_instance: The `main` application instance.
            value: The value returned from the Chatbot AFTER it ran `send_email`.
            args: Additional arguments passed to the callback.
        """
        try:
            if value:
                main_instance._xlog.debug("📧 Email sent.")
                main_instance.show_arbitrary_text_on_eink(
                    icon="📧",
                    text="Email sent ✅",
                    font_size=EinkCanvas.FONT_BIG_SIZE)
            else:
                main_instance._xlog.error("🛑 Failed to send email.")
                main_instance.show_arbitrary_text_on_eink(
                    icon="📧",
                    text="Failed to send email ❌",
                    font_size=EinkCanvas.FONT_BIG_SIZE)
        except Exception as e:
            main_instance._xlog.error(f"🛑 Error in email callback: {e}")
    
    def get_tool_definition(self) -> list[callable]:
        """
        Returns the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.send_email]
    
    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Gets the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        if function_name == "send_email":
            return self.callback_send_email