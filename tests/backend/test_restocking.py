"""
Tests for restocking API endpoints (recommendations and restock orders).
"""
import pytest

from mock_data import restock_orders


@pytest.fixture(autouse=True)
def reset_restock_orders():
    """Clear the shared in-memory restock_orders list so tests don't leak state into each other."""
    restock_orders.clear()
    yield
    restock_orders.clear()


class TestRestockRecommendationsEndpoint:
    """Test suite for the budget-driven restock recommendations endpoint."""

    def test_get_recommendations_returns_all_forecast_items(self, client):
        """Test that recommendations include every demand forecast item."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 9

    def test_get_recommendations_structure(self, client):
        """Test that recommendation items have the expected structure and types."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        data = response.json()

        first_item = data[0]
        assert "item_sku" in first_item
        assert "item_name" in first_item
        assert "current_demand" in first_item
        assert "forecasted_demand" in first_item
        assert "trend" in first_item
        assert "unit_cost" in first_item
        assert "recommended_quantity" in first_item
        assert "estimated_cost" in first_item
        assert "urgency_rank" in first_item
        assert "selected" in first_item

        assert isinstance(first_item["current_demand"], int)
        assert isinstance(first_item["forecasted_demand"], int)
        assert isinstance(first_item["unit_cost"], (int, float))
        assert isinstance(first_item["recommended_quantity"], int)
        assert isinstance(first_item["estimated_cost"], (int, float))
        assert isinstance(first_item["urgency_rank"], int)
        assert isinstance(first_item["selected"], bool)

    def test_get_recommendations_zero_budget_selects_nothing(self, client):
        """Test that a zero budget selects no items."""
        response = client.get("/api/restocking/recommendations?budget=0")
        data = response.json()

        assert all(item["selected"] is False for item in data)

    def test_get_recommendations_large_budget_selects_all(self, client):
        """Test that a very large budget selects every item."""
        response = client.get("/api/restocking/recommendations?budget=999999")
        data = response.json()

        assert all(item["selected"] is True for item in data)

    def test_get_recommendations_urgency_ordering(self, client):
        """Test that increasing-trend items rank ahead of stable, and stable ahead of decreasing."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        data = response.json()

        ranks_by_trend = {"increasing": [], "stable": [], "decreasing": []}
        for item in data:
            ranks_by_trend[item["trend"]].append(item["urgency_rank"])

        if ranks_by_trend["increasing"] and ranks_by_trend["stable"]:
            assert max(ranks_by_trend["increasing"]) < min(ranks_by_trend["stable"])
        if ranks_by_trend["stable"] and ranks_by_trend["decreasing"]:
            assert max(ranks_by_trend["stable"]) < min(ranks_by_trend["decreasing"])

    def test_get_recommendations_budget_greedy_fill_respects_budget(self, client):
        """Test that the total estimated cost of selected items never exceeds the budget."""
        budget = 1000
        response = client.get(f"/api/restocking/recommendations?budget={budget}")
        data = response.json()

        total_selected_cost = sum(item["estimated_cost"] for item in data if item["selected"])
        assert total_selected_cost <= budget

    def test_get_recommendations_estimated_cost_calculation(self, client):
        """Test that estimated cost equals unit cost times recommended quantity."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        data = response.json()

        for item in data:
            expected_cost = round(item["unit_cost"] * item["recommended_quantity"], 2)
            assert abs(item["estimated_cost"] - expected_cost) < 0.01


class TestRestockOrdersEndpoint:
    """Test suite for submitting and retrieving restock orders."""

    def test_get_restock_orders_returns_list(self, client):
        """Test that fetching restock orders returns a list."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_create_restock_order_success(self, client):
        """Test submitting a valid restock order."""
        payload = {
            "item_sku": "WDG-001",
            "item_name": "Industrial Widget Type A",
            "quantity": 150,
            "unit_cost": 45.00,
            "trend": "increasing"
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["item_sku"] == "WDG-001"
        assert data["quantity"] == 150
        assert data["status"] == "Processing"
        assert abs(data["total_cost"] - (150 * 45.00)) < 0.01
        assert "id" in data
        assert "created_date" in data
        assert "expected_delivery_date" in data

    @pytest.mark.parametrize("trend,expected_lead_time", [
        ("increasing", 5),
        ("stable", 10),
        ("decreasing", 14),
    ])
    def test_create_restock_order_lead_time_by_trend(self, client, trend, expected_lead_time):
        """Test that lead time is derived from the item's demand trend."""
        payload = {
            "item_sku": "TEST-SKU",
            "item_name": "Test Item",
            "quantity": 10,
            "unit_cost": 5.00,
            "trend": trend
        }
        response = client.post("/api/restock-orders", json=payload)
        data = response.json()

        assert data["lead_time_days"] == expected_lead_time
        assert "T" in data["expected_delivery_date"]

    def test_create_restock_order_invalid_quantity(self, client):
        """Test that a non-positive quantity is rejected."""
        payload = {
            "item_sku": "WDG-001",
            "item_name": "Industrial Widget Type A",
            "quantity": 0,
            "unit_cost": 45.00,
            "trend": "increasing"
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_create_restock_order_invalid_unit_cost(self, client):
        """Test that a non-positive unit cost is rejected."""
        payload = {
            "item_sku": "WDG-001",
            "item_name": "Industrial Widget Type A",
            "quantity": 10,
            "unit_cost": 0,
            "trend": "increasing"
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data

    def test_create_restock_order_invalid_trend(self, client):
        """Test that a trend outside increasing/stable/decreasing is rejected."""
        payload = {
            "item_sku": "WDG-001",
            "item_name": "Industrial Widget Type A",
            "quantity": 10,
            "unit_cost": 45.00,
            "trend": "skyrocketing"
        }
        response = client.post("/api/restock-orders", json=payload)
        assert response.status_code == 422

    def test_create_restock_order_ids_are_unique_under_concurrent_submission(self, client):
        """Test that submitting several orders back-to-back never produces duplicate IDs
        (regression test for the len(restock_orders)+1 ID collision that concurrent
        Promise.all submissions from the Restocking view could trigger)."""
        payload = {
            "item_sku": "WDG-001",
            "item_name": "Industrial Widget Type A",
            "quantity": 10,
            "unit_cost": 45.00,
            "trend": "increasing"
        }
        ids = [client.post("/api/restock-orders", json=payload).json()["id"] for _ in range(10)]
        assert len(set(ids)) == len(ids)

    def test_create_restock_order_appears_in_list(self, client):
        """Test that a submitted restock order shows up in the restock orders list."""
        payload = {
            "item_sku": "GSK-203",
            "item_name": "High-Temperature Gasket",
            "quantity": 100,
            "unit_cost": 12.75,
            "trend": "increasing"
        }
        create_response = client.post("/api/restock-orders", json=payload)
        created_order = create_response.json()

        list_response = client.get("/api/restock-orders")
        all_orders = list_response.json()

        matching_ids = [order["id"] for order in all_orders if order["id"] == created_order["id"]]
        assert len(matching_ids) == 1
