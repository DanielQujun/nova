# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack Foundation
# All Rights Reserved.
#
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


from nova.compute import task_states
from nova.compute import vm_mode
from nova import exception
from nova import test
from nova.tests.virt.xenapi import stubs
from nova.virt import fake
from nova.virt.xenapi import driver as xenapi_conn
from nova.virt.xenapi import fake as xenapi_fake
from nova.virt.xenapi import vm_utils
from nova.virt.xenapi import vmops


class VMOpsTestCase(test.TestCase):
    def setUp(self):
        super(VMOpsTestCase, self).setUp()
        self._setup_mock_vmops()

    def _setup_mock_vmops(self, product_brand=None, product_version=None):
        self._session = self._get_mock_session(product_brand, product_version)
        self._vmops = vmops.VMOps(self._session, fake.FakeVirtAPI())

    def _get_mock_session(self, product_brand, product_version):
        class Mock(object):
            pass

        mock_session = Mock()
        mock_session.product_brand = product_brand
        mock_session.product_version = product_version
        return mock_session

    def test_check_resize_func_name_defaults_to_VDI_resize(self):
        self.assertEquals(
            'VDI.resize',
            self._vmops.check_resize_func_name())

    def _test_finish_revert_migration_after_crash(self, backup_made, new_made):
        instance = {'name': 'foo',
                    'task_state': task_states.RESIZE_MIGRATING}

        self.mox.StubOutWithMock(vm_utils, 'lookup')
        self.mox.StubOutWithMock(self._vmops, '_destroy')
        self.mox.StubOutWithMock(vm_utils, 'set_vm_name_label')
        self.mox.StubOutWithMock(self._vmops, '_attach_mapped_block_devices')
        self.mox.StubOutWithMock(self._vmops, '_start')

        vm_utils.lookup(self._session, 'foo-orig').AndReturn(
            backup_made and 'foo' or None)
        vm_utils.lookup(self._session, 'foo').AndReturn(
            (not backup_made or new_made) and 'foo' or None)
        if backup_made:
            if new_made:
                self._vmops._destroy(instance, 'foo')
            vm_utils.set_vm_name_label(self._session, 'foo', 'foo')
            self._vmops._attach_mapped_block_devices(instance, [])
        self._vmops._start(instance, 'foo')

        self.mox.ReplayAll()

        self._vmops.finish_revert_migration(instance, [])

    def test_finish_revert_migration_after_crash(self):
        self._test_finish_revert_migration_after_crash(True, True)

    def test_finish_revert_migration_after_crash_before_new(self):
        self._test_finish_revert_migration_after_crash(True, False)

    def test_finish_revert_migration_after_crash_before_backup(self):
        self._test_finish_revert_migration_after_crash(False, False)

    def test_determine_vm_mode_returns_xen(self):
        self.mox.StubOutWithMock(vm_mode, 'get_from_instance')

        fake_instance = "instance"
        vm_mode.get_from_instance(fake_instance).AndReturn(vm_mode.XEN)

        self.mox.ReplayAll()
        self.assertEquals(vm_mode.XEN,
            self._vmops._determine_vm_mode(fake_instance, None, None))
        self.mox.VerifyAll()

    def test_determine_vm_mode_returns_hvm(self):
        self.mox.StubOutWithMock(vm_mode, 'get_from_instance')

        fake_instance = "instance"
        vm_mode.get_from_instance(fake_instance).AndReturn(vm_mode.HVM)

        self.mox.ReplayAll()
        self.assertEquals(vm_mode.HVM,
            self._vmops._determine_vm_mode(fake_instance, None, None))
        self.mox.VerifyAll()

    def test_determine_vm_mode_returns_is_pv(self):
        self.mox.StubOutWithMock(vm_mode, 'get_from_instance')
        self.mox.StubOutWithMock(vm_utils, 'determine_is_pv')

        fake_instance = {"os_type": "foo"}
        fake_vdis = {'root': {"ref": 'fake'}}
        fake_disk_type = "disk"
        vm_mode.get_from_instance(fake_instance).AndReturn(None)
        vm_utils.determine_is_pv(self._session, "fake", fake_disk_type,
            "foo").AndReturn(True)

        self.mox.ReplayAll()
        self.assertEquals(vm_mode.XEN,
            self._vmops._determine_vm_mode(fake_instance, fake_vdis,
                                     fake_disk_type))
        self.mox.VerifyAll()

    def test_determine_vm_mode_returns_is_not_pv(self):
        self.mox.StubOutWithMock(vm_mode, 'get_from_instance')
        self.mox.StubOutWithMock(vm_utils, 'determine_is_pv')

        fake_instance = {"os_type": "foo"}
        fake_vdis = {'root': {"ref": 'fake'}}
        fake_disk_type = "disk"
        vm_mode.get_from_instance(fake_instance).AndReturn(None)
        vm_utils.determine_is_pv(self._session, "fake", fake_disk_type,
            "foo").AndReturn(False)

        self.mox.ReplayAll()
        self.assertEquals(vm_mode.HVM,
            self._vmops._determine_vm_mode(fake_instance, fake_vdis,
                                     fake_disk_type))
        self.mox.VerifyAll()

    def test_determine_vm_mode_returns_is_not_pv_no_root_disk(self):
        self.mox.StubOutWithMock(vm_mode, 'get_from_instance')
        self.mox.StubOutWithMock(vm_utils, 'determine_is_pv')

        fake_instance = {"os_type": "foo"}
        fake_vdis = {'iso': {"ref": 'fake'}}
        fake_disk_type = "disk"
        vm_mode.get_from_instance(fake_instance).AndReturn(None)

        self.mox.ReplayAll()
        self.assertEquals(vm_mode.HVM,
            self._vmops._determine_vm_mode(fake_instance, fake_vdis,
                                     fake_disk_type))
        self.mox.VerifyAll()

    def test_xsm_sr_check_relaxed_cached(self):
        self.make_plugin_call_count = 0

        def fake_make_plugin_call(plugin, method, **args):
            self.make_plugin_call_count = self.make_plugin_call_count + 1
            return "true"

        self.stubs.Set(self._vmops, "_make_plugin_call",
                       fake_make_plugin_call)

        self.assertTrue(self._vmops._is_xsm_sr_check_relaxed())
        self.assertTrue(self._vmops._is_xsm_sr_check_relaxed())

        self.assertEqual(self.make_plugin_call_count, 1)

    def test_destroy_raises_when_shutdown_fails(self):
        vm_ref = "vm_reference"
        fake_instance = "instance"

        self.mox.StubOutWithMock(vm_utils, 'hard_shutdown_vm')
        vm_utils.hard_shutdown_vm(self._session, fake_instance,
                                  vm_ref).AndReturn(False)
        self.mox.ReplayAll()
        self.assertRaises(exception.InstancePowerOffFailure,
                          self._vmops._destroy, fake_instance, vm_ref)


class GetConsoleOutputTestCase(stubs.XenAPITestBase):
    def setUp(self):
        super(GetConsoleOutputTestCase, self).setUp()
        stubs.stubout_session(self.stubs, xenapi_fake.SessionBase)
        self._session = xenapi_conn.XenAPISession('test_url', 'root',
                'test_pass', fake.FakeVirtAPI())
        self.vmops = vmops.VMOps(self._session, fake.FakeVirtAPI())
        self.vms = []

    def tearDown(self):
        super(GetConsoleOutputTestCase, self).tearDown()
        for vm in self.vms:
            xenapi_fake.destroy_vm(vm)

    def _create_vm(self, name, state):
        vm = xenapi_fake.create_vm(name, state)
        self.vms.append(vm)
        return vm

    def test_get_console_output_works(self):
        self.mox.StubOutWithMock(self.vmops, '_get_dom_id')

        instance = {"name": "dummy"}
        self.vmops._get_dom_id(instance, check_rescue=True).AndReturn(42)
        self.mox.ReplayAll()

        self.assertEqual("dom_id: 42", self.vmops.get_console_output(instance))

    def test_get_console_output_throws_nova_exception(self):
        self.mox.StubOutWithMock(self.vmops, '_get_dom_id')

        instance = {"name": "dummy"}
        # dom_id=0 used to trigger exception in fake XenAPI
        self.vmops._get_dom_id(instance, check_rescue=True).AndReturn(0)
        self.mox.ReplayAll()

        self.assertRaises(exception.NovaException,
                self.vmops.get_console_output, instance)

    def test_get_dom_id_works(self):
        instance = {"name": "dummy"}
        vm_ref = self._create_vm("dummy", "Running")
        vm_rec = xenapi_fake.get_record("VM", vm_ref)

        self.assertEqual(vm_rec["domid"], self.vmops._get_dom_id(instance))

    def test_get_dom_id_works_with_rescue_vm(self):
        instance = {"name": "dummy"}
        vm_ref = self._create_vm("dummy-rescue", "Running")
        vm_rec = xenapi_fake.get_record("VM", vm_ref)

        self.assertEqual(vm_rec["domid"],
                self.vmops._get_dom_id(instance, check_rescue=True))

    def test_get_dom_id_raises_not_found(self):
        instance = {"name": "dummy"}
        vm_ref = self._create_vm("notdummy", "Running")
        vm_rec = xenapi_fake.get_record("VM", vm_ref)

        self.assertRaises(exception.NotFound,
                self.vmops._get_dom_id, instance)

    def test_get_dom_id_works_with_vmref(self):
        instance = {"name": "dummy"}
        vm_ref = self._create_vm("dummy", "Running")
        vm_rec = xenapi_fake.get_record("VM", vm_ref)

        self.assertEqual(vm_rec["domid"],
                self.vmops._get_dom_id(vm_ref=vm_ref))
