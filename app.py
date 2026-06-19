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
* **Evening:** Depending on your policy, expired backlogs are either carried forward or cancelled as Lost Sales. 
""")

# ==========================================
# 1. SIDEBAR: Inputs & Parameters
# ==========================================
st.sidebar.header("⚙️ Simulation Controls")

# NEW: Button to trigger a rerun with a new random demand generation
if st.sidebar.button("🔄 Generate New Demand", type="primary", use_container_width=True):
    # Streamlit scripts run top-to-bottom on interaction. 
    # Pressing this button inherently triggers a fresh run with new random numbers.
    pass

st.sidebar.markdown("---")

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

demands_array = np.maximum(0, np.random.normal(mean_demand, std_demand, sim_days).astype(int))

# Pre-allocate arrays for standard daily ledger
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

# Pre-allocate arrays for Cohort Lifecycle Tracking
arr_cohort_fills = np.zeros((sim_days, sim_days), dtype=int) 
arr_cohort_lost = np.zeros(sim_days, dtype=int)

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
        order_idx = order['order_day'] - 1
        days_late = day - order['order_day']
        
        if inventory >= order['qty']:
            arr_cohort_fills[order_idx, days_late] += order['qty'] 
            inventory -= order['qty']
            daily_fulfilled += order['qty']
            if day <= order['due_day']:
                total_fulfilled_on_time += order['qty']
        elif inventory > 0:
            arr_cohort_fills[order_idx, days_late] += inventory 
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
    today_idx = day - 1
    
    if daily_demand > 0:
        due_day = day + service_time
        today_order = {'order_day': day, 'due_day': due_day, 'qty': daily_demand}
        
        if inventory >= today_order['qty']:
            arr_cohort_fills[today_idx, 0] += today_order['qty'] 
            inventory -= today_order['qty']
            daily_fulfilled += today_order['qty']
            total_fulfilled_on_time += today_order['qty']
        elif inventory > 0:
            arr_cohort_fills[today_idx, 0] += inventory 
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
    
    # True Stockout Check & Lost Sales Execution
    past_due_orders = [o for o in customer_queue if day >= o['due_day']]
    arr_stockout_day[i] = 1 if len(past_due_orders) > 0 else 0
    
    daily_lost_sales = 0
    if cancel_expired and len(past_due_orders) > 0:
        daily_lost_sales = sum(o['qty'] for o in past_due_orders)
        
        for o in past_due_orders:
            arr_cohort_lost[o['order_day'] - 1] += o['qty']
            
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

# ==========================================
# 3. BUILD DATAFRAMES
# ==========================================

# 1. Standard Ledger DataFrame
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

# 2. Cohort Analysis DataFrame
col_sums = np.sum(arr_cohort_fills, axis=0)
max_delay_idx = np.max(np.nonzero(col_sums)) if np.any(col_sums) else 0

cohort_df = pd.DataFrame({
    'Demand Day': np.arange(1, sim_days + 1),
    'Total Demand': demands_array,
})

for d in range(max_delay_idx + 1):
    col_name = 'Filled (Same Day)' if d == 0 else f'Filled (+{d} Days)'
    cohort_df[col_name] = arr_cohort_fills[:, d]

cohort_df['Unsold (Lost)'] = arr_cohort_lost

arr_cohort_pending = np.zeros(sim_days, dtype=int)
for order in customer_queue:
    arr_cohort_pending[order['order_day'] - 1] += order['qty']
cohort_df['Pending (In Queue)'] = arr_cohort_pending

# 3. Fulfillment Summary Table (OTIF)
summary_data = []
for d in range(max_delay_idx + 1):
    label = "Same Day" if d == 0 else f"+{d} Days"
    qty = col_sums[d]
    pct = (qty / total_demand_generated) * 100 if total_demand_generated > 0 else 0
    summary_data.append({
        "Fulfillment Time": label, 
        "Total Units": qty, 
        "% of Total Demand": f"{pct:.2f}%"
    })

total_lost_sales = df['Lost Sales (Cancelled)'].sum()
lost_pct = (total_lost_sales / total_demand_generated) * 100 if total_demand_generated > 0 else 0
summary_data.append({
    "Fulfillment Time": "Unsold (Lost)", 
    "Total Units": total_lost_sales, 
    "% of Total Demand": f"{lost_pct:.2f}%"
})

total_pending = np.sum(arr_cohort_pending)
pending_pct = (total_pending / total_demand_generated) * 100 if total_demand_generated > 0 else 0
summary_data.append({
    "Fulfillment Time": "Pending (In Queue)", 
    "Total Units": total_pending, 
    "% of Total Demand": f"{pending_pct:.2f}%"
})

summary_df = pd.DataFrame(summary_data)


# ==========================================
# 4. OUTPUTS & KPIs
# ==========================================
stockout_days = df['Stockout Day'].sum()
min_inv = df['Closing Balance'].min()
max_inv = df['Closing Balance'].max()
avg_inv = df['Closing Balance'].mean()
max_backlog = df['Backlogs to Carry Forward'].max()
fill_rate = (total_fulfilled_on_time / total_demand_generated) * 100 if total_demand_generated > 0 else 100

st.header("📊 Key Performance Indicators")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Stockout Days", f"{stockout_days} days", delta=f"{(stockout_days/sim_days)*100:.1f}% of time", delta_color="inverse")
col2.metric("Fill Rate (On-Time)", f"{fill_rate:.2f}%")
col3.metric("Max Backlog", f"{max_backlog:,.0f} units")

# NEW: Lost Sales metric dynamically shows % of total demand as the delta
col4.metric("Total Lost Sales", f"{total_lost_sales:,.0f} units", 
            delta=f"{lost_pct:.2f}% of Total Demand", delta_color="inverse")

st.markdown("<br>", unsafe_allow_html=True)

col5, col6, col7, col8 = st.columns(4)
col5.metric("Min Inventory", f"{min_inv:,.0f} units")
col6.metric("Max Inventory", f"{max_inv:,.0f} units")
col7.metric("Avg Inventory", f"{avg_inv:,.0f} units")
col8.metric("Total Demand", f"{total_demand_generated:,.0f} units")

# ==========================================
# 5. OTIF BREAKDOWN KPIs
# ==========================================
st.markdown("---")
st.subheader("⏱️ On-Time In-Full (OTIF) Breakdown")
st.markdown("Tracking exactly what percentage of total demand was fulfilled relative to the allowed Service Time.")

# Render OTIF columns only up to the configured Service Time to keep it clean
otif_cols = st.columns(service_time + 1)
for d in range(service_time + 1):
    if d <= max_delay_idx:
        qty = col_sums[d]
        pct = (qty / total_demand_generated) * 100 if total_demand_generated > 0 else 0
    else:
        qty, pct = 0, 0
        
    label = "OTIF (Same Day)" if d == 0 else f"OTIF (+{d} Days)"
    otif_cols[d].metric(label, f"{pct:.2f}%", f"{qty:,.0f} units", delta_color="off")


# ==========================================
# 6. VISUALIZATIONS
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
                 name='Lost Sales (Cancelled)', marker_color='#ffaa00', opacity=0.9)
               
st.plotly_chart(fig3, use_container_width=True)

# ==========================================
# 7. DATA TABLES
# ==========================================
st.markdown("---")
st.subheader("📊 Fulfillment Summary")
st.markdown("A high-level summary of exactly how long it took to fulfill the generated demand.")
st.dataframe(summary_df, use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("🔍 Order Fulfillment Cohort Analysis (Detailed)")
st.markdown("Read horizontally to see exactly when the demand generated on a specific day was finally shipped to the customer (or if it was lost).")
st.dataframe(cohort_df, use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("📋 Daily Warehouse Ledger")
st.markdown("Detailed breakdown of daily operations, inventory balances, and order pipelines.")

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
