from scripts.run_competition_tests import parse_junit


def test_junit_failures_and_skips_are_not_counted_as_passes(tmp_path):
    junit = tmp_path / 'results.xml'
    junit.write_text('''<testsuite>
      <testcase classname="tests.test_example" name="ok" time="0.1" />
      <testcase classname="tests.test_example" name="broken" time="0.2"><failure message="wrong value" /></testcase>
      <testcase classname="tests.test_example" name="unavailable" time="0"><skipped /></testcase>
    </testsuite>''', encoding='utf-8')
    result = parse_junit(junit)
    assert (result['total'], result['passed'], result['failed'], result['skipped']) == (3, 1, 1, 1)
    assert result['failures'][0]['case'] == 'broken'
