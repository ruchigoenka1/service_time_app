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
* **Evening:** Depending on your policy, expired backlogs are either carried forward or cancelled as Lost Sales. Inventory position is evaluated for reordering.
""")

# ==========================================
# 1. SIDEBAR: Inputs & Parameters
# ==========================================
st.sidebar.header("⚙️ Simulation Parameters")

st.sidebar.subheader("Demand Profile")
mean_demand = st.sidebar.number_input("Average Daily Demand", min_value=1, value=50)
std_demand = st.sidebar.number_input("Demand Variation (Std Dev)", min_value=0, value=15)

st.sidebar.subheader("Time Metrics (Days)")
supplier_lead_time = st.sidebar.number_input("Supplier Lead Time (LT)", min_value=1, value=14, 
                                             help="Orders placed evening of Day T arrive morning of Day T + LT + 1")
service_time = st.sidebar.number_input("Service Time (Backlog Allowance)", min_value=0, value=2, 
                                       help="Days an order can sit in the backlog before the timer expires.")

st.sidebar.subheader("Backlog Policy")
backlog_policy = st.sidebar.radio(
    "What happens when Service Time expires?",
    options=["Carry Forward (Keep trying to fill)", "Cancel Order (Lost Sale)"],
    help="Determines if expired orders sit in the queue forever, or get deleted as a Lost Sale."
)
cancel_expired = (backlog_policy == "Cancel Order (Lost Sale)")

st.sidebar.subheader("Inventory Policy")
rop = st.sidebar.number_input("Reorder Point (ROP)", min_value=0, value=800)
order_qty = st.sidebar.number_input("Order Quantity (Q)", min_value=1, value=1000)

st.sidebar.subheader("Simulation Length")
sim_days = st.sidebar.number_input("Days to Simulate", min_value=30, value=365)

# ==========================================
# 2. OPTIMIZED SIMULATION ENGINE
# ==========================================

# Vectorized Upfront Generation of Random Demands
demands_array = np.maximum(0, np.random.normal(mean_demand, std_demand, sim_days).astype(int))

# Pre-allocate NumPy arrays for ledger tracking
arr_opening_balance = np.zeros(sim_days, dtype=int)
arr_opening_backlog = np.zeros(sim_days, dtype=int)
arr_orders_fulfilled = np.zeros(sim_days, dtype=int)
arr_unfulfilled_demand = np.zeros(sim_days, dtype=int)
arr_lost_sales = np.zeros(sim_days, dtype=int) 
arr_backlog_cf = np.zeros(sim_days, dtype=int)
arr_closing_balance = np.zeros(sim_days, dtype=int)
arr_pipeline_orders = np.zeros(sim_days, dtype=int)
arr_stockout_day = np.zeros(sim_days, dtype=int)
arr_inv_position = np.zeros(sim_days, dtype=int)

# Initialize Starting State
inventory = rop + order_qty
pending_supplier_orders = [] 
customer_queue = []          

total_demand_generated = np.sum(demands_array)
total_fulfilled_on_time = 0

for i in range(sim_days):
    day = i + 1
    daily_fulfilled = 0
    daily_unfulfilled_new = 0 
    
    # --- MORNING OPERATIONS ---
    arrived_qty = sum([o['qty'] for o in pending_supplier_orders if o['arrival_day'] == day])
    inventory += arrived_qty
    pending_supplier_orders = [o for o in pending_supplier_orders if o['arrival_day'] > day]
    
    arr_opening_balance[i] = inventory
    arr_opening_backlog[i] = sum([o['qty'] for o in customer_queue])
    
    # --- CLEAR BACKLOG FIRST ---
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
    
    # --- DAYTIME NEW DEMAND ---
    daily_demand = demands_array[i]
    
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
            daily_unfulfilled_new = today_order['qty'] - inventory 
            today_order['qty'] -= inventory
            inventory = 0
            customer_queue.append(today_order)
        else:
            daily_unfulfilled_new = today_order['qty'] 
            customer_queue.append(today_order)
            
    # --- END OF DAY METRICS & REVIEW ---
    arr_closing_balance[i] = inventory
    arr_orders_fulfilled[i] = daily_fulfilled
    arr_unfulfilled_demand[i] = daily_unfulfilled_new
    
    # --- CORRECTED STOCKOUT LOGIC ---
    # An order is now flagged as a stockout if it is still in the queue on the evening of its due date
    past_due_orders = [o for o in customer_queue if day >= o['due_day']]
    arr_stockout_day[i] = 1 if len(past_due_orders) > 0 else 0
    
    daily_lost_sales = 0
    if cancel_expired and len(past_due_orders) > 0:
        daily_lost_sales = sum(o['qty'] for o in past_due_orders)
        # Drop the expired orders (keep only those whose due date is STRICTLY greater than today)
        customer_queue = [o for o in customer_queue if day < o['due_day']]
        
    arr_lost_sales[i] = daily_lost_sales
    
    # Record remaining backlog AFTER potential cancellations
    arr_backlog_cf[i] = sum(o['qty'] for o in customer_queue)
    
    # Pipeline & Inventory Position
    pipeline_qty = sum([o['qty'] for o in pending_supplier_orders])
    inv_position = arr_closing_balance[i] + pipeline_qty - arr_backlog_cf[i]
    
    # Q, R Ordering Logic
    if inv_position <= rop:
        already_ordered_today = any(o['ordered_day'] == day for o in pending_supplier_orders)
        if not already_ordered_today:
            arrival_date = day + supplier_lead_time + 1
            pending_supplier_orders.append({
                'ordered_day': day, 
                'arrival_day': arrival_date, 
                'qty': order_qty
            })
            pipeline_qty += order_qty
            
    arr_pipeline_orders[i] = pipeline_qty
    arr_inv_position[i] = inv_position

# Instantly build DataFrame from pre-allocated arrays
df = pd.DataFrame({
    'Day': np.arange(1, sim_days + 1),
    'Opening Balance': arr_opening_balance,
    'Opening Backlog Orders': arr_opening_backlog,
    'Demand': demands_array,
    'Orders Fulfilled': arr_orders_fulfilled,
    'Unfulfilled Orders (Today)': arr_unfulfilled_demand,
    'Lost Sales (Cancelled)': arr_lost_sales, 
    'Backlogs to Carry Forward': arr_backlog_cf,
    'Closing Balance': arr_closing_balance,
    'Pipeline Orders': arr_pipeline_orders,
    'Stockout Day': arr_stockout_day,
    'Inventory Position': arr_inv_position,
    'Net Inventory': arr_closing_balance - arr_backlog_cf
})

# ==========================================
# 3. OUTPUTS & KPIs
# ==========================================
stockout_days = df['Stockout Day'].sum()
min_inv = df['Closing Balance'].min()
max_inv = df['Closing Balance'].max()
avg_inv = df['Closing Balance'].mean()
max_backlog = df['Backlogs to Carry Forward'].max()
total_lost_sales = df['Lost Sales (Cancelled)'].sum()
fill_rate = (total_fulfilled_on_time / total_demand_generated) * 100 if total_demand_generated > 0 else 100

st.header("📊 Key Performance Indicators")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Stockout Days", f"{stockout_days} days", delta=f"{(stockout_days/sim_days)*100:.1f}% of time", delta_color="inverse")
col2.metric("Fill Rate (On-Time)", f"{fill_rate:.2f}%")
col3.metric("Max Backlog", f"{max_backlog:,.0f} units")
col4.metric("Total Lost Sales", f"{total_lost_sales:,.0f} units", delta="Cancelled Demand", delta_color="inverse")

st.markdown("<br>", unsafe_allow_html=True)

col5, col6, col7, col8 = st.columns(4)
col5.metric("Min Inventory", f"{min_inv:,.0f} units")
col6.metric("Max Inventory", f"{max_inv:,.0f} units")
col7.metric("Avg Inventory", f"{avg_inv:,.0f} units")
col8.metric("Total Demand", f"{total_demand_generated:,.0f} units")

# ==========================================
# 4. VISUALIZATIONS
# ==========================================
st.markdown("---")
st.subheader("📈 Inventory Level Over Time")

fig1 = px.line(df, x='Day', y=['Closing Balance', 'Inventory Position'], 
              labels={'value': 'Units', 'variable': 'Metric'},
              color_discrete_map={'Closing Balance': '#1f77b4', 'Inventory Position': '#ff7f0e'})

fig1.add_hline(y=rop, line_dash="dash", line_color="red", annotation_text="Reorder Point (ROP)")

stockout_mask = df['Stockout Day'] == 1
if stockout_mask.any():
    stockouts = df[stockout_mask]
    fig1.add_scatter(x=stockouts['Day'], y=stockouts['Closing Balance'], 
                    mode='markers', marker=dict(color='red', size=8), name='Stockout Event')
                    
st.plotly_chart(fig1, use_container_width=True)

st.markdown("---")
st.subheader("📉 Net Inventory Over Time (Closing Inventory - Backlog)")
st.markdown("Positive values reflect available shelf stock. Negative values show explicit unfulfilled order deficits.")

fig2 = px.line(df, x='Day', y='Net Inventory', 
              labels={'Net Inventory': 'Net Units'},
              color_discrete_sequence=['#9467bd']) 

fig2.add_hline(y=0, line_dash="solid", line_color="black", opacity=0.4)
st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")
st.subheader("⚠️ Backlog Accumulation & Lost Sales Over Time")

fig3 = px.area(df, x='Day', y='Backlogs to Carry Forward', 
               labels={'Backlogs to Carry Forward': 'Units'},
               color_discrete_sequence=['#d62728']) 

fig3.update_traces(name='Active Backlog', showlegend=True)

if df['Lost Sales (Cancelled)'].sum() > 0:
    fig3.add_bar(x=df['Day'], y=df['Lost Sales (Cancelled)'], 
                 name='Lost Sales (Cancelled)', marker_color='black', opacity=0.6)
               
st.plotly_chart(fig3, use_container_width=True)

# ==========================================
# 5. DAILY LEDGER TABLE
# ==========================================
st.markdown("---")
st.subheader("📋 Daily Inventory Ledger")
st.markdown("Detailed breakdown tracking Opening, Closing, Pipeline balances, and Policy executions.")

ledger_cols = [
    'Day', 
    'Opening Balance', 
    'Opening Backlog Orders', 
    'Demand', 
    'Orders Fulfilled', 
    'Unfulfilled Orders (Today)', 
    'Lost Sales (Cancelled)', 
    'Backlogs to Carry Forward', 
    'Closing Balance', 
    'Pipeline Orders'
]

st.dataframe(df[ledger_cols], use_container_width=True, hide_index=True)
