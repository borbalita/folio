from ingest.sec_tables import extract_sec_tables


def test_extract_sec_tables_simple() -> None:
    html = """
    <html><body>
    <p>Net sales</p>
    <table>
      <tr><th>Metric</th><th>2024</th></tr>
      <tr><td>Revenue</td><td>$100</td></tr>
    </table>
    </body></html>
    """
    tables = extract_sec_tables(html)
    assert len(tables) == 1
    assert tables[0].rows[0].label == "Revenue"
