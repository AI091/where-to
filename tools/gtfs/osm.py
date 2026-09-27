import requests
import json


def test_osm_transit_data():
    url = "https://overpass-api.de/api/interpreter"
    headers = {
        "User-Agent": "Mashrou3y Transit Mapper",
        "Accept": "application/json",
    }

    def run_query(name, query):
        print(f"\n{'='*70}")
        print(f"QUERY: {name}")
        print(f"{'='*70}")
        try:
            response = requests.post(url, data={"data": query}, headers=headers, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error: {e}")
            return None

    def analyze(data, label=""):
        if not data:
            return
        elements = data.get("elements", [])
        print(f"\n>>> Total elements: {len(elements)}")

        # Group by type
        by_type = {}
        all_tag_keys = set()
        all_values = {}

        for element in elements:
            el_type = element.get("type", "unknown")
            by_type.setdefault(el_type, []).append(element)

            tags = element.get("tags", {})
            for k, v in tags.items():
                all_tag_keys.add(k)
                all_values.setdefault(k, set()).add(v)

        print(f">>> By element type:")
        for t, items in sorted(by_type.items()):
            print(f"    {t}: {len(items)}")

        if all_tag_keys:
            print(f">>> All tag keys found:")
            for k in sorted(all_tag_keys):
                vals = all_values.get(k, set())
                if len(vals) <= 5:
                    print(f"    {k} = {sorted(vals)}")
                else:
                    print(f"    {k} ({len(vals)} unique values)")

        # Dump first 5 elements fully
        print(f">>> First 5 elements:")
        for i, element in enumerate(elements[:5]):
            print(f"\n  Element {i+1} ({element.get('type')} id={element.get('id')}):")
            print(json.dumps(element, indent=4, ensure_ascii=False))
        if len(elements) > 5:
            print(f"\n  ... and {len(elements) - 5} more")

    # 1. Route relations (what we had before)
    query_routes = """
    [out:json][timeout:60];
    area["name:en"="Alexandria"]->.searchArea;
    (
      relation["route"="share_taxi"](area.searchArea);
      relation["route"="tram"](area.searchArea);
      relation["route"="bus"](area.searchArea);
      relation["route"="minibus"](area.searchArea);
      relation["route"="trolleybus"](area.searchArea);
      relation["route"="subway"](area.searchArea);
    );
    out tags;
    """
    data_routes = run_query("Route Relations", query_routes)
    analyze(data_routes)

    # 2. Stops / platforms / bus stops
    query_stops = """
    [out:json][timeout:60];
    area["name:en"="Alexandria"]->.searchArea;
    (
      node["public_transport"="stop_position"](area.searchArea);
      node["public_transport"="platform"](area.searchArea);
      node["highway"="bus_stop"](area.searchArea);
      way["public_transport"="platform"](area.searchArea);
    );
    out tags;
    """
    data_stops = run_query("Stops & Platforms", query_stops)
    analyze(data_stops)

    # 3. Ways with bus-related tags
    query_ways = """
    [out:json][timeout:60];
    area["name:en"="Alexandria"]->.searchArea;
    (
      way["highway"]["bus"="yes"](area.searchArea);
      way["highway"]["trolley_wire"](area.searchArea);
    );
    out tags;
    """
    data_ways = run_query("Ways (bus=yes / trolley_wire)", query_ways)
    analyze(data_ways)

    # 4. ALL nodes with any public_transport tag
    query_all_nodes = """
    [out:json][timeout:60];
    area["name:en"="Alexandria"]->.searchArea;
    node["public_transport"](area.searchArea);
    out tags;
    """
    data_all_nodes = run_query("ALL nodes with public_transport tag", query_all_nodes)
    analyze(data_all_nodes)

    # 5. ALL ways with any public_transport tag
    query_all_ways = """
    [out:json][timeout:60];
    area["name:en"="Alexandria"]->.searchArea;
    way["public_transport"](area.searchArea);
    out tags;
    """
    data_all_ways = run_query("ALL ways with public_transport tag", query_all_ways)
    analyze(data_all_ways)


if __name__ == "__main__":
    test_osm_transit_data()
