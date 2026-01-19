import re
import random
import string
from behave import use_fixture
from odoo.tests.common import TransactionCase

SANITIZE_FEATURE_NAME_REGEX = re.compile(r'[^a-zA-Z0-9_ ]')


def feature_to_class(feature_name):
    salt = ''.join([random.choice(string.ascii_uppercase)] + [random.choice(string.ascii_lowercase) for _ in range(4)])
    sanitized_name = SANITIZE_FEATURE_NAME_REGEX.sub('', feature_name)
    truncated_name = sanitized_name.split(' ')[0][:20]
    truncated_name = truncated_name[0].upper() + truncated_name[1:]
    class_name = truncated_name + salt
    return class_name


########################################################
# fixtures
########################################################

def odoo_test_class(context):
    context.tcls = type(context.tcls_name, (context.tcls_base,), {})
    context.tcls.setUpClass()
    context.env = context.tcls.env
    yield
    context.tcls.doClassCleanups()

def odoo_test_case(context):
    context.tc = context.tcls()
    context.tc.setUp()
    context.env = context.tc.env
    yield
    context.tc.doCleanups()


########################################################
# hooks
########################################################

def before_feature(context, feature):
    if not hasattr(context, 'tcls_name'):
        context.tcls_name = feature_to_class(feature.name)
    if not hasattr(context, 'tcls_base'):
        context.tcls_base = TransactionCase
    use_fixture(odoo_test_class, context)

def before_scenario(context, scenario):
    use_fixture(odoo_test_case, context)
