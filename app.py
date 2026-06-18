import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="Inventory Flexibility Simulator", layout="wide")

st.title("📦 Inventory Dispatch Flexibility Simulator")
st.markdown("""
This app simulates a continuous review **(Q, R)** inventory system with backlog allowances.
* **Morning:** Incoming shipments arrive. Existing backlogs are cleared first.
* **Daytime:** New demand occurs and is filled. Unfilled demand moves to the backlog.
* **Evening:** Inventory position is evaluated. If below ROP, a new order is placed to arrive in **$LT + 1$** days.
""")

# ==========================================
# SIDEBAR: Inputs
# ==========================================
st.sidebar.header("⚙️ Simulation Parameters")

st.sidebar.subheader("Demand Profile")
mean_demand = st.sidebar.number_input("Average Daily Demand", min_value=1, value=50)
std_demand = st.sidebar.number_input("Demand Variation (Std Dev)", min_value=0, value=15)

st.sidebar.subheader("Time Metrics (Days)")
supplier_lead_time = st.sidebar.number_input("Supplier Lead Time (LT)", min_value=1, value=14, 
                                             help="Orders placed evening of Day T arrive morning of Day T + LT + 1")
service_time = st.sidebar.number_input("Service Time (Backlog Allowance)", min_value=0, value=3, 
                                       help="Days an order can be carried before it becomes a stockout.")

st.sidebar.subheader("Inventory Policy")
rop = st.sidebar.number_input("Reorder Point (ROP)", min_value=0, value=800)
order_qty = st.sidebar.number_input("Order Quantity (Q)", min_value=1, value=1000)

st.sidebar.subheader("Simulation Length")
sim_days = st.sidebar.number_input("Days to Simulate", min_value=30, value=365)

# ==========================================
# SIMULATION ENGINE (Runs automatically)
# ==========================================

# Initial State
inventory = rop + order_qty
pending_supplier_orders = [] # List of dicts: {'ordered_day': int, 'arrival_day': int, 'qty': int}
customer_queue = []          # List of dicts: {'order_day': int, 'due_day': int, 'qty': int}

daily_records = []
total_demand_generated = 0
total_fulfilled_on_time = 0

for day in range(1, sim_days + 1):
    daily_fulfilled = 0
    
    # 1. EARLY MORNING: Receive incoming shipments from supplier
    arrived_qty = sum([o['qty'] for o in pending_supplier_orders if o['arrival_day'] == day])
    inventory += arrived_qty
    pending_supplier_orders = [o for o in pending_supplier_orders if o['arrival_day'] > day]
    
    # Snapshot: Opening Balances
    opening_balance = inventory
    opening_backlog = sum([o['qty'] for o in customer_queue])
    
    # 2. CLEAR BACKLOG FIRST: Use available inventory to fulfill older orders
    new_queue = []
    for order in customer_queue:
        if inventory >= order['qty']:
            inventory -= order['qty']
            daily_fulfilled += order['qty']
            if day <= order['due_day']:
                total_fulfilled_on_time += order['qty']
        elif inventory > 0:
            daily_fulfilled += inventory
            if day <= order['due_day']:
                total_fulfilled_on_time += inventory
            order['qty'] -= inventory
            inventory = 0
            new_queue.append(order)
        else:
            new_queue.append(order)
            
    customer_queue = new_queue
    
    # 3. DAYTIME NEW DEMAND: Generate today's demand and fulfill if inventory remains
    daily_demand = max(0, int(np.random.normal(mean_demand, std_demand)))
    total_demand_generated += daily_demand
    
    if daily_demand > 0:
        due_day = day + service_time
        today_order = {'order_day': day, 'due_day': due_day, 'qty': daily_demand}
        
        if inventory >= today_order['qty']:
            inventory -= today_order['qty']
            daily_fulfilled += today_order['qty']
            total_fulfilled_on_time += today_order['qty']
        elif inventory > 0:
            daily_fulfilled += inventory
            total_fulfilled_on_time += inventory
            today_order['qty'] -= inventory
            inventory = 0
            customer_queue.append(today_order)
        else:
            customer_queue.append(today_order)
            
    # 4. END OF DAY METRICS
    closing_balance = inventory
    backlog_cf = sum(o['qty'] for o in customer_queue)
    
    # Check for True Stockouts (orders past their allowed service time)
    past_due_orders = [o for o in customer_queue if day >= o['due_day']]
    is_stockout = len(past_due_orders) > 0
    
    # 5. EVENING REVIEW & ORDERING (Q, R Policy)
    # Pipeline orders currently in transit (before placing a new one)
    pipeline_qty = sum([o['qty'] for o in pending_supplier_orders])
    
    # Inventory Position = On Hand + On Order - Total Backlog
    inv_position = closing_balance + pipeline_qty - backlog_cf
    
    if inv_position <= rop:
        # Prevent placing duplicate orders on the exact same day
        already_ordered_today = any(o['ordered_day'] == day for o in pending_supplier_orders)
        if not already_ordered_today:
            # Lead Time Logic: Placed Day T -> Arrives Day T + LT + 1
            arrival_date = day + supplier_lead_time + 1
            pending_supplier_orders.append({
                'ordered_day': day, 
                'arrival_day': arrival_date, 
                'qty': order_qty
            })
            # Update pipeline quantity to reflect the order just placed
            pipeline_qty += order_qty
            
    # 6. Record the day's ledger
    daily_records.append({
        'Day': day,
        'Opening Balance': opening_balance,
        'Opening Backlog Orders': opening_backlog,
        'Demand': daily_demand,
        'Orders Fulfilled': daily_fulfilled,
        'Backlogs to Carry Forward': backlog_cf,
        'Closing Balance': closing_balance,
        'Pipeline Orders': pipeline_qty,
        'Stockout Day': 1 if is_stockout else 0, # Hidden from ledger table, used for KPIs
        'Inventory Position': inv_position       # Hidden from ledger table, used for Charts
    })
    
df = pd.DataFrame(daily_records)

# ==========================================
# OUTPUTS & KPIs
# ==========================================
stockout_days = df['Stockout Day'].sum()
min_inv = df['Closing Balance'].min()
max_inv = df['Closing Balance'].max()
avg_inv = df['Closing Balance'].mean()
fill_rate = (total_fulfilled_on_time / total_demand_generated) * 100 if total_demand_generated > 0 else 100

st.header("📊 Key Performance Indicators")
col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Stockout Days", f"{stockout_days} days", 
            delta=f"{(stockout_days/sim_days)*100:.1f}% of time", delta_color="inverse")
col2.metric("Fill Rate (On-Time)", f"{fill_rate:.2f}%")
col3.metric("Min Inventory", f"{min_inv:,.0f} units")
col4.metric("Max Inventory", f"{max_inv:,.0f} units")
col5.metric("Avg Inventory", f"{avg_inv:,.0f} units")

# ==========================================
# VISUALIZATIONS
# ==========================================
st.markdown("---")
st.subheader("📈 Inventory Level Over Time")

fig = px.line(df, x='Day', y=['Closing Balance', 'Inventory Position'], 
              labels={'value': 'Units', 'variable': 'Metric'},
              color_discrete_map={'Closing Balance': '#1f77b4', 'Inventory Position': '#ff7f0e'})

fig.add_hline(y=rop, line_dash="dash", line_color="red", annotation_text="Reorder Point (ROP)")

stockout_mask = df['Stockout Day'] == 1
if stockout_mask.any():
    stockouts = df[stockout_mask]
    fig.add_scatter(x=stockouts['Day'], y=stockouts['Closing Balance'], 
                    mode='markers', marker=dict(color='red', size=8), name='Stockout (Past Due)')
                    
st.plotly_chart(fig, use_container_width=True)

# ==========================================
# DAILY LEDGER TABLE
# ==========================================
st.markdown("---")
st.subheader("📋 Daily Inventory Ledger")
st.markdown("Detailed breakdown of operations tracking Opening, Closing, and Pipeline balances.")

# Filter columns explicitly to match your request
ledger_cols = [
    'Day', 
    'Opening Balance', 
    'Opening Backlog Orders', 
    'Demand', 
    'Orders Fulfilled', 
    'Backlogs to Carry Forward', 
    'Closing Balance', 
    'Pipeline Orders'
]

st.dataframe(df[ledger_cols], use_container_width=True, hide_index=True)
