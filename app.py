import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="Inventory Flexibility Simulator", layout="wide")

st.title("📦 Inventory Dispatch Flexibility Simulator")
st.markdown("""
This app simulates a continuous review **(Q, R)** inventory system. 
By increasing the **Service Time to Customer**, you give your warehouse a grace period to fulfill orders, effectively reducing stockout days without increasing safety stock.
""")

# ==========================================
# SIDEBAR: Inputs
# ==========================================
st.sidebar.header("⚙️ Simulation Parameters")

st.sidebar.subheader("Demand Profile")
mean_demand = st.sidebar.number_input("Average Daily Demand", min_value=1, value=50)
std_demand = st.sidebar.number_input("Demand Variation (Std Dev)", min_value=0, value=15)

st.sidebar.subheader("Time Metrics (Days)")
supplier_lead_time = st.sidebar.number_input("Supplier Lead Time", min_value=1, value=14, 
                                             help="Days it takes for the supplier to deliver.")
service_time = st.sidebar.number_input("Service Time (Dispatch Flexibility)", min_value=0, value=3, 
                                       help="Days allowed before an order MUST be dispatched.")
customer_transit_time = st.sidebar.number_input("Lead Time to Customer (Transit)", min_value=0, value=2, 
                                                help="Transit time after dispatch. (Does not affect warehouse stockouts).")

st.sidebar.subheader("Inventory Policy")
rop = st.sidebar.number_input("Reorder Point (ROP)", min_value=0, value=800)
order_qty = st.sidebar.number_input("Order Quantity (Q)", min_value=1, value=1000)

st.sidebar.subheader("Simulation Length")
sim_days = st.sidebar.number_input("Days to Simulate", min_value=30, value=365)

# ==========================================
# SIMULATION ENGINE
# ==========================================
if st.sidebar.button("Run Simulation", type="primary"):
    
    # Initial State
    inventory = rop + order_qty
    pending_supplier_orders = [] # List of dicts: {'arrival_day': int, 'qty': int}
    customer_queue = []          # List of dicts: {'due_day': int, 'qty': int}
    
    daily_records = []
    total_demand_generated = 0
    total_fulfilled_on_time = 0
    
    # Run the daily loop
    for day in range(1, sim_days + 1):
        
        # 1. Receive incoming shipments from supplier
        arrived_qty = sum([o['qty'] for o in pending_supplier_orders if o['arrival_day'] == day])
        inventory += arrived_qty
        pending_supplier_orders = [o for o in pending_supplier_orders if o['arrival_day'] > day]
        
        # 2. Generate today's random demand
        daily_demand = max(0, int(np.random.normal(mean_demand, std_demand)))
        total_demand_generated += daily_demand
        
        # 3. Add to customer queue with a due date
        if daily_demand > 0:
            due_day = day + service_time
            customer_queue.append({'due_day': due_day, 'qty': daily_demand})
            
        # 4. Fulfill orders (FIFO by due date)
        customer_queue.sort(key=lambda x: x['due_day'])
        new_queue = []
        
        for order in customer_queue:
            if inventory >= order['qty']:
                inventory -= order['qty']
                if day <= order['due_day']:
                    total_fulfilled_on_time += order['qty']
            elif inventory > 0:
                # Partial fulfillment
                if day <= order['due_day']:
                    total_fulfilled_on_time += inventory
                order['qty'] -= inventory
                inventory = 0
                new_queue.append(order)
            else:
                # No inventory left to fulfill this order
                new_queue.append(order)
                
        customer_queue = new_queue
        
        # 5. Check for Stockouts (Past due orders + zero inventory)
        past_due_orders = [o for o in customer_queue if o['due_day'] < day]
        is_stockout = len(past_due_orders) > 0
        backlog_qty = sum(o['qty'] for o in past_due_orders)
        
        # 6. Check Reorder Point
        # Inventory Position = On Hand + On Order - Total Backlog
        on_order = sum([o['qty'] for o in pending_supplier_orders])
        total_backlog = sum([o['qty'] for o in customer_queue])
        inv_position = inventory + on_order - total_backlog
        
        if inv_position <= rop:
            pending_supplier_orders.append({'arrival_day': day + supplier_lead_time, 'qty': order_qty})
            
        # 7. Record the day's metrics
        daily_records.append({
            'Day': day,
            'Inventory On Hand': inventory,
            'Inventory Position': inv_position,
            'Stockout Day': 1 if is_stockout else 0,
            'Backlog Qty': backlog_qty
        })
        
    df = pd.DataFrame(daily_records)
    
    # ==========================================
    # OUTPUTS & KPIs
    # ==========================================
    stockout_days = df['Stockout Day'].sum()
    min_inv = df['Inventory On Hand'].min()
    max_inv = df['Inventory On Hand'].max()
    avg_inv = df['Inventory On Hand'].mean()
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
    
    fig = px.line(df, x='Day', y=['Inventory On Hand', 'Inventory Position'], 
                  labels={'value': 'Units', 'variable': 'Metric'},
                  color_discrete_map={'Inventory On Hand': '#1f77b4', 'Inventory Position': '#ff7f0e'})
    
    # Add ROP line
    fig.add_hline(y=rop, line_dash="dash", line_color="red", annotation_text="Reorder Point (ROP)")
    
    # Highlight Stockout periods
    stockout_mask = df['Stockout Day'] == 1
    if stockout_mask.any():
        # Scatter points for days with actual past-due backlog
        stockouts = df[stockout_mask]
        fig.add_scatter(x=stockouts['Day'], y=stockouts['Inventory On Hand'], 
                        mode='markers', marker=dict(color='red', size=8), name='Stockout (Past Due)')
                        
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    st.subheader("📋 Daily Simulation Data")
    st.dataframe(df, use_container_width=True)

else:
    st.info("👈 Adjust your parameters in the sidebar and click **Run Simulation** to see the results.")
