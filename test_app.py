import unittest
from unittest.mock import patch
import app as module

class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        module.recent.clear()
        self.client=module.app.test_client()
        self.token=module.signer.dumps({'id':'test-visit'})
    def payload(self, role='маг', word='бурмалда'):
        return {'character':role,'word':word,'token':self.token}
    def test_three_roles(self):
        for role in module.ROLES:
            with patch('app.send_email') as mail:
                result=self.client.post('/api/confirm',json=self.payload(role,' БУРМАЛДА '))
                self.assertEqual(result.status_code,200)
                mail.assert_called_once_with(role,'test-visit')
    def test_wrong_word_and_forged_token_never_send(self):
        with patch('app.send_email') as mail:
            self.assertEqual(self.client.post('/api/confirm',json=self.payload(word='ні')).status_code,400)
            p=self.payload();p['token']='forged'
            self.assertEqual(self.client.post('/api/confirm',json=p).status_code,403)
            mail.assert_not_called()
    def test_missing_mail_config_is_not_success(self):
        with patch('app.send_email',side_effect=RuntimeError('mail_not_configured')):
            self.assertEqual(self.client.post('/api/confirm',json=self.payload()).status_code,503)
    def test_page(self):
        result=self.client.get('/')
        self.assertEqual(result.status_code,200)
        self.assertIn(b'/api/confirm',result.data)
        self.assertNotIn(b'{{ token',result.data)

if __name__=='__main__': unittest.main()
