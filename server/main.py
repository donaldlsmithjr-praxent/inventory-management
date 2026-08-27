from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Literal, Optional
from datetime import datetime, timedelta
from uuid import uuid4
from pydantic import BaseModel
from mock_data import inventory_items, orders, demand_forecasts, backlog_items, spending_summary, monthly_spending, category_spending, recent_transactions, purchase_orders, restock_orders, tasks

app = FastAPI(title="Factory Inventory Management System")

# Quarter mapping for date filtering
QUARTER_MAP = {
    'Q1-2025': ['2025-01', '2025-02', '2025-03'],
    'Q2-2025': ['2025-04', '2025-05', '2025-06'],
    'Q3-2025': ['2025-07', '2025-08', '2025-09'],
    'Q4-2025': ['2025-10', '2025-11', '2025-12']
}

def filter_by_month(items: list, month: Optional[str]) -> list:
    """Filter items by month/quarter based on order_date field"""
    if not month or month == 'all':
        return items

    if month.startswith('Q'):
        # Handle quarters
        if month in QUARTER_MAP:
            months = QUARTER_MAP[month]
            return [item for item in items if any(m in item.get('order_date', '') for m in months)]
    else:
        # Direct month match
        return [item for item in items if month in item.get('order_date', '')]

    return items

def apply_filters(items: list, warehouse: Optional[str] = None, category: Optional[str] = None,
                 status: Optional[str] = None) -> list:
    """Apply common filters to a list of items"""
    filtered = items

    if warehouse and warehouse != 'all':
        filtered = [item for item in filtered if item.get('warehouse') == warehouse]

    if category and category != 'all':
        filtered = [item for item in filtered if item.get('category', '').lower() == category.lower()]

    if status and status != 'all':
        filtered = [item for item in filtered if item.get('status', '').lower() == status.lower()]

    return filtered

# Urgency tiers for restock recommendations (higher = more urgent)
TREND_URGENCY = {'increasing': 3, 'stable': 2, 'decreasing': 1}

# Simulated delivery lead time by demand trend (no lead-time data exists in the source data)
LEAD_TIME_DAYS = {'increasing': 5, 'stable': 10, 'decreasing': 14}

def compute_restock_recommendations(budget: float) -> list:
    """Rank demand forecast items by urgency (trend + demand gap) and greedily
    mark items as selected while they still fit within the remaining budget"""
    enriched = []
    for forecast in demand_forecasts:
        demand_gap = forecast['forecasted_demand'] - forecast['current_demand']
        estimated_cost = round(forecast['unit_cost'] * forecast['recommended_quantity'], 2)
        enriched.append({**forecast, 'demand_gap': demand_gap, 'estimated_cost': estimated_cost})

    # Most urgent trend tier first, then largest demand gap, then SKU for a stable order
    enriched.sort(key=lambda item: (-TREND_URGENCY[item['trend']], -item['demand_gap'], item['item_sku']))

    remaining_budget = budget
    result = []
    for rank, item in enumerate(enriched, start=1):
        fits = item['estimated_cost'] <= remaining_budget
        if fits:
            remaining_budget -= item['estimated_cost']
        result.append({
            'item_sku': item['item_sku'],
            'item_name': item['item_name'],
            'current_demand': item['current_demand'],
            'forecasted_demand': item['forecasted_demand'],
            'trend': item['trend'],
            'unit_cost': item['unit_cost'],
            'recommended_quantity': item['recommended_quantity'],
            'estimated_cost': item['estimated_cost'],
            'urgency_rank': rank,
            'selected': fits,
        })
    return result

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data models
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    category: str
    warehouse: str
    quantity_on_hand: int
    reorder_point: int
    unit_cost: float
    location: str
    last_updated: str

class Order(BaseModel):
    id: str
    order_number: str
    customer: str
    items: List[dict]
    status: str
    order_date: str
    expected_delivery: str
    total_value: float
    actual_delivery: Optional[str] = None
    warehouse: Optional[str] = None
    category: Optional[str] = None

class DemandForecast(BaseModel):
    id: str
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    period: str
    unit_cost: float
    recommended_quantity: int

class BacklogItem(BaseModel):
    id: str
    order_id: str
    item_sku: str
    item_name: str
    quantity_needed: int
    quantity_available: int
    days_delayed: int
    priority: str
    has_purchase_order: Optional[bool] = False

class PurchaseOrder(BaseModel):
    id: str
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    status: str
    created_date: str
    notes: Optional[str] = None

class CreatePurchaseOrderRequest(BaseModel):
    backlog_item_id: str
    supplier_name: str
    quantity: int
    unit_cost: float
    expected_delivery_date: str
    notes: Optional[str] = None

class RestockRecommendation(BaseModel):
    item_sku: str
    item_name: str
    current_demand: int
    forecasted_demand: int
    trend: str
    unit_cost: float
    recommended_quantity: int
    estimated_cost: float
    urgency_rank: int
    selected: bool

class CreateRestockOrderRequest(BaseModel):
    item_sku: str
    item_name: str
    quantity: int
    unit_cost: float
    trend: Literal["increasing", "stable", "decreasing"]

class RestockOrder(BaseModel):
    id: str
    item_sku: str
    item_name: str
    quantity: int
    unit_cost: float
    total_cost: float
    trend: str
    status: str
    created_date: str
    lead_time_days: int
    expected_delivery_date: str

class Task(BaseModel):
    id: str
    title: str
    priority: str
    dueDate: str
    status: str

class CreateTaskRequest(BaseModel):
    title: str
    priority: str
    dueDate: str

# API endpoints
@app.get("/")
def root():
    return {"message": "Factory Inventory Management System API", "version": "1.0.0"}

@app.get("/api/inventory", response_model=List[InventoryItem])
def get_inventory(
    warehouse: Optional[str] = None,
    category: Optional[str] = None
):
    """Get all inventory items with optional filtering"""
    return apply_filters(inventory_items, warehouse, category)

@app.get("/api/inventory/{item_id}", response_model=InventoryItem)
def get_inventory_item(item_id: str):
    """Get a specific inventory item"""
    item = next((item for item in inventory_items if item["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.get("/api/orders", response_model=List[Order])
def get_orders(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get all orders with optional filtering"""
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)
    return filtered_orders

@app.get("/api/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    """Get a specific order"""
    order = next((order for order in orders if order["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@app.get("/api/demand", response_model=List[DemandForecast])
def get_demand_forecasts():
    """Get demand forecasts"""
    return demand_forecasts

@app.get("/api/backlog", response_model=List[BacklogItem])
def get_backlog():
    """Get backlog items with purchase order status"""
    # Add has_purchase_order flag to each backlog item
    result = []
    for item in backlog_items:
        item_dict = dict(item)
        # Check if this backlog item has a purchase order
        has_po = any(po["backlog_item_id"] == item["id"] for po in purchase_orders)
        item_dict["has_purchase_order"] = has_po
        result.append(item_dict)
    return result

@app.get("/api/restocking/recommendations", response_model=List[RestockRecommendation])
def get_restock_recommendations(budget: float = 0.0):
    """Get budget-driven restock recommendations ranked by urgency (trend + demand gap)"""
    return compute_restock_recommendations(budget)

@app.get("/api/restock-orders", response_model=List[RestockOrder])
def get_restock_orders():
    """Get all submitted restock orders"""
    return restock_orders

@app.post("/api/restock-orders", response_model=RestockOrder)
def create_restock_order(request: CreateRestockOrderRequest):
    """Submit a restock order for a recommended item"""
    if request.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")
    if request.unit_cost <= 0:
        raise HTTPException(status_code=400, detail="Unit cost must be positive")

    created_date = datetime.now().isoformat()
    lead_time_days = LEAD_TIME_DAYS[request.trend]
    expected_delivery_date = (datetime.now() + timedelta(days=lead_time_days)).isoformat()

    new_order = {
        # uuid4 avoids the len()+1 collision that concurrent submissions (Promise.all on the frontend) would hit
        "id": str(uuid4()),
        "item_sku": request.item_sku,
        "item_name": request.item_name,
        "quantity": request.quantity,
        "unit_cost": request.unit_cost,
        "total_cost": round(request.quantity * request.unit_cost, 2),
        "trend": request.trend,
        "status": "Processing",
        "created_date": created_date,
        "lead_time_days": lead_time_days,
        "expected_delivery_date": expected_delivery_date,
    }
    restock_orders.append(new_order)
    return new_order

@app.get("/api/purchase-orders", response_model=List[PurchaseOrder])
def get_purchase_orders():
    """Get all purchase orders"""
    return purchase_orders

@app.post("/api/purchase-orders", response_model=PurchaseOrder)
def create_purchase_order(request: CreatePurchaseOrderRequest):
    """Create a purchase order for a backlog item"""
    if request.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")
    if request.unit_cost <= 0:
        raise HTTPException(status_code=400, detail="Unit cost must be positive")

    new_po = {
        "id": str(uuid4()),
        "backlog_item_id": request.backlog_item_id,
        "supplier_name": request.supplier_name,
        "quantity": request.quantity,
        "unit_cost": request.unit_cost,
        "expected_delivery_date": request.expected_delivery_date,
        "status": "Pending",
        "created_date": datetime.now().isoformat(),
        "notes": request.notes,
    }
    purchase_orders.append(new_po)
    return new_po

@app.get("/api/tasks", response_model=List[Task])
def get_tasks():
    """Get all tasks"""
    return tasks

@app.post("/api/tasks", response_model=Task)
def create_task(request: CreateTaskRequest):
    """Create a new task"""
    new_task = {
        "id": str(uuid4()),
        "title": request.title,
        "priority": request.priority,
        "dueDate": request.dueDate,
        "status": "pending",
    }
    tasks.append(new_task)
    return new_task

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task"""
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks.remove(task)
    return {"message": "Task deleted"}

@app.patch("/api/tasks/{task_id}", response_model=Task)
def toggle_task(task_id: str):
    """Toggle a task's completion status"""
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task["status"] = "completed" if task["status"] == "pending" else "pending"
    return task

@app.get("/api/dashboard/summary")
def get_dashboard_summary(
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None
):
    """Get summary statistics for dashboard with optional filtering"""
    # Filter inventory
    filtered_inventory = apply_filters(inventory_items, warehouse, category)

    # Filter orders
    filtered_orders = apply_filters(orders, warehouse, category, status)
    filtered_orders = filter_by_month(filtered_orders, month)

    total_inventory_value = sum(item["quantity_on_hand"] * item["unit_cost"] for item in filtered_inventory)
    low_stock_items = len([item for item in filtered_inventory if item["quantity_on_hand"] <= item["reorder_point"]])
    pending_orders = len([order for order in filtered_orders if order["status"] in ["Processing", "Backordered"]])
    total_backlog_items = len(backlog_items)

    return {
        "total_inventory_value": round(total_inventory_value, 2),
        "low_stock_items": low_stock_items,
        "pending_orders": pending_orders,
        "total_backlog_items": total_backlog_items,
        "total_orders_value": sum(order["total_value"] for order in filtered_orders)
    }

@app.get("/api/spending/summary")
def get_spending_summary():
    """Get spending summary statistics"""
    return spending_summary

@app.get("/api/spending/monthly")
def get_monthly_spending():
    """Get monthly spending breakdown"""
    return monthly_spending

@app.get("/api/spending/categories")
def get_category_spending():
    """Get spending by category"""
    return category_spending

@app.get("/api/spending/transactions")
def get_recent_transactions():
    """Get recent transactions"""
    return recent_transactions

@app.get("/api/reports/quarterly")
def get_quarterly_reports():
    """Get quarterly performance reports"""
    # Calculate quarterly statistics from orders
    quarters = {}

    for order in orders:
        order_date = order.get('order_date', '')
        # Determine quarter
        if '2025-01' in order_date or '2025-02' in order_date or '2025-03' in order_date:
            quarter = 'Q1-2025'
        elif '2025-04' in order_date or '2025-05' in order_date or '2025-06' in order_date:
            quarter = 'Q2-2025'
        elif '2025-07' in order_date or '2025-08' in order_date or '2025-09' in order_date:
            quarter = 'Q3-2025'
        elif '2025-10' in order_date or '2025-11' in order_date or '2025-12' in order_date:
            quarter = 'Q4-2025'
        else:
            continue

        if quarter not in quarters:
            quarters[quarter] = {
                'quarter': quarter,
                'total_orders': 0,
                'total_revenue': 0,
                'delivered_orders': 0,
                'avg_order_value': 0
            }

        quarters[quarter]['total_orders'] += 1
        quarters[quarter]['total_revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            quarters[quarter]['delivered_orders'] += 1

    # Calculate averages and fulfillment rate
    result = []
    for q, data in quarters.items():
        if data['total_orders'] > 0:
            data['avg_order_value'] = round(data['total_revenue'] / data['total_orders'], 2)
            data['fulfillment_rate'] = round((data['delivered_orders'] / data['total_orders']) * 100, 1)
        result.append(data)

    # Sort by quarter
    result.sort(key=lambda x: x['quarter'])
    return result

@app.get("/api/reports/monthly-trends")
def get_monthly_trends():
    """Get month-over-month trends"""
    months = {}

    for order in orders:
        order_date = order.get('order_date', '')
        if not order_date:
            continue

        # Extract month (format: YYYY-MM-DD)
        month = order_date[:7]  # Gets YYYY-MM

        if month not in months:
            months[month] = {
                'month': month,
                'order_count': 0,
                'revenue': 0,
                'delivered_count': 0
            }

        months[month]['order_count'] += 1
        months[month]['revenue'] += order.get('total_value', 0)
        if order.get('status') == 'Delivered':
            months[month]['delivered_count'] += 1

    # Convert to list and sort
    result = list(months.values())
    result.sort(key=lambda x: x['month'])
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
