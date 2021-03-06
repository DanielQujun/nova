#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_config import cfg

from nova.api.openstack.placement import direct
from nova.api.openstack.placement.objects import resource_provider
from nova import context
from nova import test
from nova.tests import fixtures
from nova.tests import uuidsentinel


CONF = cfg.CONF


# FIXME(cdent): some dupes with db/test_base.py
class TestDirect(test.NoDBTestCase):
    USES_DB_SELF = True

    def setUp(self):
        super(TestDirect, self).setUp()
        self.api_db = self.useFixture(fixtures.Database(database='placement'))
        self._reset_traits_synced()
        self.context = context.get_admin_context()
        self.addCleanup(self._reset_traits_synced)

    @staticmethod
    def _reset_traits_synced():
        """Reset the _TRAITS_SYNCED boolean to base state."""
        resource_provider._TRAITS_SYNCED = False

    def test_direct_is_there(self):
        with direct.PlacementDirect(CONF) as client:
            resp = client.get('/')
            self.assertTrue(resp)
            data = resp.json()
            self.assertEqual('v1.0', data['versions'][0]['id'])

    def test_get_resource_providers(self):
        with direct.PlacementDirect(CONF) as client:
            resp = client.get('/resource_providers')
            self.assertTrue(resp)
            data = resp.json()
            self.assertEqual([], data['resource_providers'])

    def test_create_resource_provider(self):
        data = {'name': 'fake'}
        with direct.PlacementDirect(CONF) as client:
            resp = client.post('/resource_providers', json=data)
            self.assertTrue(resp)
            resp = client.get('/resource_providers')
            self.assertTrue(resp)
            data = resp.json()
            self.assertEqual(1, len(data['resource_providers']))

    def test_json_validation_happens(self):
        data = {'name': 'fake', 'cowsay': 'moo'}
        with direct.PlacementDirect(CONF) as client:
            # TODO(efried): Set raise_exc globally when
            # https://review.openstack.org/#/c/574784/ is released.
            resp = client.post('/resource_providers', json=data,
                               raise_exc=False)
            self.assertFalse(resp)
            self.assertEqual(400, resp.status_code)

    def test_microversion_handling(self):
        with direct.PlacementDirect(CONF) as client:
            # create parent
            parent_data = {'name': uuidsentinel.p_rp,
                           'uuid': uuidsentinel.p_rp}
            resp = client.post('/resource_providers', json=parent_data)
            self.assertTrue(resp, resp.text)

            # attempt to create child
            data = {'name': 'child', 'parent_provider_uuid': uuidsentinel.p_rp}
            # no microversion, 400
            resp = client.post('/resource_providers', json=data,
                               raise_exc=False)
            self.assertFalse(resp)
            self.assertEqual(400, resp.status_code)
            # low microversion, 400
            resp = client.post('/resource_providers', json=data,
                               raise_exc=False, microversion='1.13')
            self.assertFalse(resp)
            self.assertEqual(400, resp.status_code)
            resp = client.post('/resource_providers', json=data,
                               microversion='1.14')
            self.assertTrue(resp, resp.text)
