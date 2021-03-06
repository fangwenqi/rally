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

import collections
import json
import re

from rally.ui import utils
from rally.verification import reporter


SKIP_RE = re.compile("Skipped until Bug: ?(?P<bug_number>\d+) is resolved.")
LP_BUG_LINK = "https://launchpad.net/bugs/%s"


@reporter.configure("json")
class JSONReporter(reporter.VerificationReporter):
    """Generates verification report in JSON format."""

    # ISO 8601
    TIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"

    @classmethod
    def validate(cls, output_destination):
        """Validate destination of report.

        :param output_destination: Destination of report
        """
        # nothing to check :)
        pass

    def _generate(self):
        """Prepare raw report."""

        verifications = collections.OrderedDict()
        tests = {}

        for v in self.verifications:
            verifications[v.uuid] = {
                "started_at": v.created_at.strftime(self.TIME_FORMAT),
                "finished_at": v.updated_at.strftime(self.TIME_FORMAT),
                "status": v.status,
                "run_args": v.run_args,
                "tests_count": v.tests_count,
                "tests_duration": v.tests_duration,
                "skipped": v.skipped,
                "success": v.success,
                "expected_failures": v.expected_failures,
                "unexpected_success": v.unexpected_success,
                "failures": v.failures,
            }

            for test_id, result in v.tests.items():
                if test_id not in tests:
                    # NOTE(ylobankov): It is more convenient to see test ID
                    #                  at the first place in the report.
                    tags = sorted(result.get("tags", []), reverse=True,
                                  key=lambda tag: tag.startswith("id-"))
                    tests[test_id] = {"tags": tags,
                                      "name": result["name"],
                                      "by_verification": {}}

                tests[test_id]["by_verification"][v.uuid] = {
                    "status": result["status"],
                    "duration": result["duration"]
                }

                reason = result.get("reason", "")
                if reason:
                    match = SKIP_RE.match(reason)
                    if match:
                        link = LP_BUG_LINK % match.group("bug_number")
                        reason = re.sub(match.group("bug_number"), link,
                                        reason)
                traceback = result.get("traceback", "")
                sep = "\n\n" if reason and traceback else ""
                d = (reason + sep + traceback.strip()) or None
                if d:
                    tests[test_id]["by_verification"][v.uuid]["details"] = d

        return {"verifications": verifications, "tests": tests}

    def generate(self):
        raw_report = json.dumps(self._generate(), indent=4)

        if self.output_destination:
            return {"files": {self.output_destination: raw_report},
                    "open": self.output_destination}
        else:
            return {"print": raw_report}


@reporter.configure("html")
class HTMLReporter(JSONReporter):
    """Generates verification report in HTML format."""
    INCLUDE_LIBS = False

    # "T" separator of ISO 8601 is not user-friendly enough.
    TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    def generate(self):
        report = self._generate()
        uuids = report["verifications"].keys()
        show_comparison_note = False

        for test in report["tests"].values():
            # make as much as possible processing here to reduce processing
            # at JS side
            test["has_details"] = False
            for test_info in test["by_verification"].values():
                if "details" not in test_info:
                    test_info["details"] = None
                elif not test["has_details"]:
                    test["has_details"] = True

            durations = []
            # iter by uuids to store right order for comparison
            for uuid in uuids:
                if uuid in test["by_verification"]:
                    durations.append(test["by_verification"][uuid]["duration"])
                    if float(durations[-1]) < 0.001:
                        durations[-1] = "0"
                        # not to display such little duration in the report
                        test["by_verification"][uuid]["duration"] = ""

                    if len(durations) > 1 and not (
                            durations[0] == "0" and durations[-1] == "0"):
                        # compare result with result of the first verification
                        diff = float(durations[-1]) - float(durations[0])
                        result = "%s (" % durations[-1]
                        if diff >= 0:
                            result += "+"
                        result += "%s)" % diff
                        test["by_verification"][uuid]["duration"] = result

            if not show_comparison_note and len(durations) > 2:
                # NOTE(andreykurilin): only in case of comparison of more
                #   than 2 results of the same test we should display a note
                #   about the comparison strategy
                show_comparison_note = True

        template = utils.get_template("verification/report.html")
        context = {"uuids": uuids,
                   "verifications": report["verifications"],
                   "tests": report["tests"],
                   "show_comparison_note": show_comparison_note}

        raw_report = template.render(data=json.dumps(context),
                                     include_libs=self.INCLUDE_LIBS)

        # in future we will support html_static and will need to save more
        # files
        if self.output_destination:
            return {"files": {self.output_destination: raw_report},
                    "open": self.output_destination}
        else:
            return {"print": raw_report}


@reporter.configure("html-static")
class HTMLStaticReporter(HTMLReporter):
    """Generates verification report in HTML format with embedded JS/CSS."""
    INCLUDE_LIBS = True
