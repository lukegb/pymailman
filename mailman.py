import requests
from bs4 import BeautifulSoup

DEFAULT_MAILMAN_INSTANCE = 'https://mailman.ic.ac.uk/mailman/'

class MailmanException(Exception):
    pass

class AuthorizationFailed(MailmanException):
    pass

class MailmanInterface(object):
    def __init__(self, mailing_list, admin_password, instance=None):
        self.mailing_list = mailing_list
        self.admin_password = admin_password
        self.instance_root = instance or DEFAULT_MAILMAN_INSTANCE
        self._session = None
        self._session_primed = False

    def session(self):
        if not self._session:
            self._session = requests.session()

        if not self._session_primed:
            self.prime_session(self._session)

        return self._session

    def prime_session(self, session):
        # log in to mailman
        session.get(self.url_admin_root) # just in case - prime cookies

        # actually perform the login step
        resp = session.post(self.url_admin_root, data=self._build_login_form_data())
        resp.raise_for_status()

        # XXX: hack to see if the log in worked OK
        if 'Authorization\nfailed.' in resp.text:
            raise AuthorizationFailed

        self._session_primed = True

    @property
    def url_admin_root(self):
        return '{}admin/{}/'.format(self.instance_root, self.mailing_list)

    @property
    def url_admin_members_mass_subscription(self):
        return '{}members/add/'.format(self.url_admin_root)

    def _build_login_form_data(self, admin_password=None):
        admin_password = admin_password or self.admin_password
        return {
            'adminpw': admin_password,
            'admlogin': 'Let me in...',
        }

    def _build_subscription_form_data(self, members_list, invite_to_list=False, send_welcome_message=False, notify_list_owner=False, invitation_text=''):
        based = {
            'subscribe_or_invite': int(invite_to_list), # 0 = subscribe, 1 = invite
            'send_welcome_msg_to_this_batch': int(send_welcome_message), # 0 = no, 1 = yes
            'send_notifications_to_list_owner': int(notify_list_owner), # 0 = no, 1 = yes
            'subscribees': '\n'.join(members_list), # newline separated members list
            'invitation': invitation_text or '',
            'setmemberopts_btn': 'Submit Your Changes',
        }
        return dict([(str(k), str(v)) for (k, v) in based.iteritems()]) # reencode everything as strings

    def membership_resp_parse(self, resp):
        soup = BeautifulSoup(resp, "html5lib")
        # NB: make sure you use a "proper" HTML parser. Otherwise the lis will become nested and will not parse correctly.
        # this is because mailman does not emit closing tags!

        success = []
        failed = []

        ok_sub = soup.find("h5", text="Successfully subscribed:")
        if ok_sub:
            ok_sub_ul = ok_sub.find_next_sibling("ul")
            for ok_sub_li in ok_sub_ul.find_all("li"):
                success.append(ok_sub_li.get_text().strip())

        failed_sub = soup.find("h5", text="Error subscribing:")
        if failed_sub:
            failed_sub_ul = failed_sub.find_next_sibling("ul")
            for failed_sub_li in failed_sub_ul.find_all("li"):
                email, _, reason = failed_sub_li.get_text().strip().partition(' -- ')
                failed.append((email, reason))

        return success, failed

    def add_members(self, new_emails, **kwargs):
        # add the members!
        data = self._build_subscription_form_data(members_list=new_emails, **kwargs)

        # NB: I use files to force as multipart/form-data encoded request
        resp = self.session().post(self.url_admin_members_mass_subscription, files=data)
        resp.raise_for_status()

        return self.membership_resp_parse(resp.text)
