import unittest

from xsimlab.variable.base import (Variable, VariableList, VariableGroup,
                                   diagnostic)
from xsimlab.process import Process


class MyProcess(Process):
    var = Variable(())
    var_list = VariableList([Variable(()), Variable(())])
    var_group = VariableGroup('group')
    no_var = 'this is not a variable object'

    class Meta:
        time_dependent = False

    @diagnostic
    def diag(self):
        return 1


class TestProcessBase(unittest.TestCase):

    def test_new(self):
        with self.assertRaisesRegex(TypeError, "subclassing a subclass"):
            class InvalidProcess(MyProcess):
                var = Variable(())

        with self.assertRaisesRegex(AttributeError, "invalid attribute"):
            class InvalidProcess2(Process):
                class Meta:
                    time_dependent = True
                    invalid_meta_attr = 'invalid'

        # test extract variable objects vs. other attributes
        self.assertTrue(getattr(MyProcess, 'no_var', False))
        self.assertFalse(getattr(MyProcess, 'var', False))
        self.assertEqual(set(['var', 'var_list', 'var_group', 'diag']),
                         set(MyProcess._variables.keys()))

        # test Meta attributes
        self.assertDictEqual(MyProcess._meta, {'time_dependent': False})


class TestProcess(unittest.TestCase):

    def setUp(self):
        self.my_process = MyProcess()

    def test_constructor(self):
        # test dict-like vs. attribute access
        self.assertIs(self.my_process['var'], self.my_process._variables['var'])
        self.assertIs(self.my_process.var, self.my_process._variables['var'])

        # test deep copy variable objects
        MyProcess._variables['var'].state = 2
        self.assertNotEqual(self.my_process._variables['var'].state,
                            MyProcess._variables['var'].state)

        # test assign process to diagnostics
        self.assertIs(self.my_process['diag']._process_obj, self.my_process)

    def test_clone(self):
        cloned_process = self.my_process.clone()
        self.assertIsNot(self.my_process['var'], cloned_process['var'])

    def test_variables(self):
        self.assertEqual(set(['var', 'var_list', 'var_group', 'diag']),
                         set(self.my_process.variables.keys()))

    def test_meta(self):
        self.assertDictEqual(self.my_process.meta, {'time_dependent': False})

    def test_name(self):
        self.assertEqual(self.my_process.name, "MyProcess")

        self.my_process._name = "my_process"
        self.assertEqual(self.my_process.name, "my_process")

    def test_run_step(self):
        with self.assertRaisesRegex(NotImplementedError, "no method"):
            self.my_process.run_step(1)