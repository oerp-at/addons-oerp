import io
import os
import glob
import time
import threading
import unittest
import logging
from tabulate import tabulate

import odoo
from odoo.tools.config import config
from odoo.service.server import ThreadedServer

from . import Command
from .assemble import CommandMixin, get_server_dir, is_addon, ConfigException


_logger = logging.getLogger(__name__)


class Test(CommandMixin, Command):
    """ Run Tests """

    def __init__(self):
        super(Test, self).__init__()
        self.parser.add_argument(
            "--test-prefix",
            metavar="TEST_PREFIX",
            required=False,
            help="Specify the prefix of the method for filtering")
        self.parser.add_argument("--test-case",
                                 metavar="TEST_CASE",
                                 required=False,
                                 help="Specify the test case")
        self.parser.add_argument(
            "--test-download",
            metavar="TEST_DOWNLOAD",
            required=False,
            help="Specify test download diretory (e.g. for reports)")
        self.parser.add_argument("--test-tags",
                                 metavar="TEST_TAGS",
                                 required=False,
                                 help="Specify test tags")
        self.parser.add_argument(
            "--test-position",
            metavar="TEST_POSITION",
            required=False,
            help="Specify position tags: post_install, at_install")

        self.parser.add_argument(
            "--test-addons",
            help="Only test modules inside addons path like custom-addons/*",
            action="append",
            required=False,

        )

        self.parser.add_argument(
            "--test-server",
            help="Run test server for web tests",
            action="store_true",
            default=True,
            required=False
        )


        self.parser.add_argument(
            "--xml-report",
            help="Generate standard XML unit test report",
            metavar="XML_REPORT"
        )

        self.xml_runner = None
        self.xml_report_data = io.BytesIO()

    def run_config(self):
        if self.params.test_download:
            config["test_download"] = self.params.test_download

        # run with env
        self.setup_env()

    def _get_test_runner(self):

        class OdooTestRunner(object):
            """A test runner class that displays results in in logger.
            Simplified verison of TextTestRunner(
            """

            def run(self, test):
                result = odoo.tests.result.OdooTestResult()
                start_time = time.perf_counter()
                test(result)
                time_taken = time.perf_counter() - start_time
                run = result.testsRun
                _logger.info("Ran %d test%s in %.3fs", run, run != 1 and "s" or "", time_taken)
                return result

        if self.params.xml_report:
            if self.xml_runner is None:
                from xmlrunner import XMLTestRunner
                self.xml_runner = XMLTestRunner(output=self.xml_report_data)
            return self.xml_runner
        else:
            return OdooTestRunner()

    def _get_server(self):
        server = ThreadedServer(odoo.http.root)
        return server

    def run_test(self,
                 module_name,
                 test_prefix=None,
                 test_case=None,
                 test_tags=None,
                 test_position=None):

        # before running tests ensure all imports
        import odoo.tests.loader
        import odoo.tests.result
        from odoo.tests.suite import OdooSuite
        from odoo.tests.loader import get_module_test_cases
        from odoo.tests.tag_selector import TagsSelector  # Avoid import loop
        from ..modules import module

        # define filter and get modules
        def match_filter(test):
            if not test_prefix or not isinstance(test, unittest.TestCase):
                if not test_case:
                    return True
                return type(test).__name__ == test_case
            return test._testMethodName.startswith(test_prefix)

        mods = odoo.tests.loader.get_test_modules(module_name)

        # set testing flags
        threading.current_thread().testing = True
        module.current_test = module_name

        # query modules, tests and run
        config_tags = TagsSelector(test_tags) if test_tags else None
        position_tag = TagsSelector(test_position) if test_position else None
        test_server_enabled = config.get('test_server', False)
        results = []
        for m in mods:
            tests = get_module_test_cases(m)
            suite = OdooSuite(
                t for t in tests
                if (not position_tag or position_tag.check(t))
                   and (not config_tags or config_tags.check(t))
                   and match_filter(t)
                   and (not isinstance(t, odoo.tests.common.HttpCase) or test_server_enabled)
            )

            if suite.countTestCases():
                t0 = time.time()
                t0_sql = odoo.sql_db.sql_counter
                _logger.info('%s running tests.', m.__name__)
                result = self._get_test_runner().run(suite)
                results.append({
                    "module": module_name,
                    "test":  m.__name__,
                    "name":  m.__name__.split(".")[-1],
                    "time": time.time() - t0,
                    "queries": odoo.sql_db.sql_counter - t0_sql,
                    "ok": result.wasSuccessful(),
                    "result": result
                })

        # remove testing flags
        module.current_test = None
        threading.current_thread().testing = False

        return results

    def run_config_env(self, env):
        # important to be here, that it not conflicts
        # with tag parsing
        config["test_enable"] = True
        config["stop_after_init"] = True
        config["test_server"] = config.get("test_server", self.params.test_server)

        module_name = self.params.module
        test_prefix = self.params.test_prefix
        test_case = self.params.test_case
        test_tags = self.params.test_tags
        test_position = self.params.test_position
        cr = env.cr

        if self.params.module:
            modules = [self.params.module]
        else:
            cr.execute(
                "SELECT name from ir_module_module WHERE state = 'installed' ")
            modules = [name for (name, ) in cr.fetchall()]

        if self.params.test_addons:
            dir_server = get_server_dir()
            dir_workspace = os.path.abspath(os.path.join(dir_server, ".."))

            allowed_modules = set()
            for addons_dir_pattern in self.params.test_addons:
                if not addons_dir_pattern.startswith('/'):
                    addons_dir_pattern = f"{dir_workspace}/{addons_dir_pattern}"
                for dir_addon in glob.glob(addons_dir_pattern):
                    if os.path.isdir(dir_addon) and is_addon(dir_addon):
                        allowed_modules.add(os.path.basename(dir_addon))

            modules = [m for m in modules if m in allowed_modules]


        results = []
        if modules:
            # start test server for http tests
            if not odoo.service.server.server:
                server = self._get_server() if config.get("test_server") else None
                if server:
                    _logger.info('Start test server')
                    server.start()
                    # assign running server
                    odoo.service.server.server = server

            # run tests
            for module_name in modules:
                results.extend(self.run_test(module_name, test_prefix, test_case,
                                   test_tags, test_position))


        if not results:
            _logger.warning("No tests!")
        else:
            # write xml report if used
            if self.params.xml_report:
                from xmlrunner.extra.xunit_plugin import transform
                with open(self.params.xml_report, 'wb') as f:
                    f.write(transform(self.xml_report_data.getvalue()))

            failed = list(filter(lambda r: not r["ok"], results))
            successful = list(filter(lambda r: r["ok"], results))
            result_txt = tabulate(
                [
                    [
                        r["module"],
                        r["name"],
                        f"{r['time']:.2f}s",
                        str(r["queries"]),
                        r["ok"] and "OK" or "FAILED"
                    ] for r in successful + failed
                ],
                tablefmt="github",
                headers=['Module','Test','Time','Queries','Status'])

            if not failed:
                _logger.info("\n\n%s\n\n", result_txt)
                _logger.info("%s Test(s) successful!", len(results))
            else:
                _logger.warning("\n\n%s\n\n", result_txt)
                raise ConfigException(f"{len(failed)}/{len(results)} Test(s) failed!")
