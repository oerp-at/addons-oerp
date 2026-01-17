from behave import fixture, use_fixture
from odoo.tests.common import TransactionCase


########################################################
# wrappers
########################################################

# simple wrapper for test class
def case_class_wrapper(context, cls):
    cls.setUpClass()
    context.tcls = cls
    yield
    cls.doClassCleanups()
    context.tcls = None

# wrapper for test instance
def case_instance(context):
    if hasattr(context, 'tcls'):
        context.tc = context.tcls()
        context.tc.setUp()
        context.env = context.tc.env
        yield
        context.tc.doCleanups()
        context.env = None
    else:
        yield


########################################################
# fixtures
########################################################

def transaction_case_class(context):
    yield from case_class_wrapper(context, TransactionCase)


########################################################
# hooks
########################################################

def before_feature(context, feature):
    use_fixture(transaction_case_class, context)

def before_scenario(context, scenario):
    use_fixture(case_instance, context)
