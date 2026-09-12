import streamlit as st
import pandas as pd
import uuid
import plotly.express as px
from datetime import datetime
from databricks import sql

# ==========================================
# Config & Database Setup
# ==========================================
st.set_page_config(page_title="FinGuard Unified Fraud Platform", layout="wide")

# Unity Catalog targets
CATALOG = "aegis_fraud_workspace"
SCHEMA = "finguard"
TABLE_ALERTS = f"{CATALOG}.{SCHEMA}.gold_fraud_alerts"
TABLE_DISPOSITIONS = f"{CATALOG}.{SCHEMA}.gold_analyst_dispositions"

@st.cache_resource(ttl=300)
def get_db_connection():
    try:
        return sql.connect(
            server_hostname=st.secrets["DATABRICKS_SERVER_HOSTNAME"],
            http_path=st.secrets["DATABRICKS_HTTP_PATH"],
            access_token=st.secrets["DATABRICKS_TOKEN"]
        )
    except KeyError as e:
        st.error(f"⚠️ Missing required key in .streamlit/secrets.toml: {e}")
        st.stop()
    except Exception as e:
        st.error(f"⚠️ SQL Warehouse Connection Failed: {e}")
        st.stop()

# ==========================================
# Data Loading Functions
# ==========================================

@st.cache_data(ttl=120)
def load_historical_metrics():
    """Loads alert records for visual analytics."""
    query = f"""
        SELECT 
            transaction_id, 
            user_id, 
            event_timestamp, 
            amount, 
            location, 
            home_city,
            segment, 
            anomaly_score, 
            is_threat
        FROM {TABLE_ALERTS}
        ORDER BY event_timestamp DESC
        LIMIT 2000
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(query)
            result = cursor.fetchall()
            cols = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(result, columns=cols)
            if not df.empty:
                df['event_timestamp'] = pd.to_datetime(df['event_timestamp'])
                df['risk_tier'] = df['anomaly_score'].apply(
                    lambda x: 'High Anomaly' if x < -0.05 else ('Moderate Anomaly' if x < 0.0 else 'Low Risk')
                )
            return df
    except Exception as e:
        st.error(f"Error loading historical data: {e}")
        return pd.DataFrame()

def load_pending_alerts():
    """Loads transactions not yet reviewed via anti-join."""
    query = f"""
        SELECT 
            a.transaction_id, 
            a.user_id, 
            a.event_timestamp, 
            a.amount, 
            a.location,
            a.home_city, 
            a.segment, 
            a.daily_limit, 
            a.anomaly_score, 
            a.sar_narrative
        FROM {TABLE_ALERTS} a
        LEFT JOIN {TABLE_DISPOSITIONS} d 
            ON a.transaction_id = d.transaction_id
        WHERE d.transaction_id IS NULL
        ORDER BY a.anomaly_score ASC
        LIMIT 100
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(query)
            result = cursor.fetchall()
            cols = [desc[0] for desc in cursor.description]
            return pd.DataFrame(result, columns=cols)
    except Exception as e:
        st.error(f"Lakehouse Connection Error: {e}")
        return pd.DataFrame()

def record_disposition(transaction_id, user_id, action, notes):
    """Writes immutable audit row back to Delta Lake using parameterized execution."""
    disp_id = f"DSP_{uuid.uuid4().hex[:10].upper()}"
    timestamp = datetime.utcnow()
    analyst_id = "ANALYST_L1_OPS"

    insert_sql = f"""
        INSERT INTO {TABLE_DISPOSITIONS} 
        (disposition_id, transaction_id, user_id, disposition_status, analyst_notes, reviewed_at, reviewed_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(insert_sql, (disp_id, transaction_id, user_id, action, notes, timestamp, analyst_id))
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Audit Trail Write Failed: {e}")
        return False

# ==========================================
# Main UI
# ==========================================

st.title("🛡️ FinGuard Unified Fraud Platform")
st.caption("End-to-End Anomaly Detection, Triage & Compliance Audit Loop | Databricks Lakehouse Native")

# Sidebar
with st.sidebar:
    st.header("Platform Status")
    st.success("🟢 Connected to Unity Catalog")
    st.info(f"📍 Schema: `{CATALOG}.{SCHEMA}`")
    st.caption("Powered by Serverless SQL Warehouses")
    
    if st.button("Refresh All Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

tab_dash, tab_triage = st.tabs(["📊 Executive Analytics Dashboard", "🚨 Analyst Investigation Triage"])

# ==========================================
# TAB 1: EXECUTIVE DASHBOARD
# ==========================================
with tab_dash:
    st.subheader("Platform Risk Overview")
    df_hist = load_historical_metrics()
    
    if df_hist.empty:
        st.info("No alert records found. Run the ingestion pipeline to populate data.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        total_alerts = len(df_hist)
        flagged_volume = df_hist['amount'].sum()
        confirmed_threats = int(df_hist['is_threat'].sum()) if 'is_threat' in df_hist.columns else 0
        impacted_users = df_hist['user_id'].nunique()

        m1.metric("Total Scored Records", f"{total_alerts:,}")
        m2.metric("Flagged Volume", f"${flagged_volume:,.2f}")
        m3.metric("Confirmed Rule Threats", f"{confirmed_threats:,}")
        m4.metric("Unique Accounts", f"{impacted_users:,}")

        st.divider()
        c1, c2 = st.columns(2)

        with c1:
            st.write("#### Anomaly Score Distribution")
            fig_hist = px.histogram(
                df_hist, 
                x="anomaly_score", 
                nbins=25, 
                color="risk_tier",
                labels={'anomaly_score': 'Isolation Forest Score', 'count': 'Frequency'}
            )
            st.plotly_chart(fig_hist, use_container_width=True)

        with c2:
            st.write("#### Alerts by Customer Segment")
            df_seg = df_hist.groupby('segment').size().reset_index(name='count')
            fig_seg = px.pie(df_seg, values='count', names='segment', hole=0.4)
            st.plotly_chart(fig_seg, use_container_width=True)

        st.write("#### Top Transaction Origin Cities")
        df_loc = df_hist.groupby('location').size().reset_index(name='count').sort_values('count', ascending=False).head(10)
        fig_loc = px.bar(df_loc, x='location', y='count', labels={'location': 'City', 'count': 'Alert Volume'}, color='count')
        st.plotly_chart(fig_loc, use_container_width=True)

# ==========================================
# TAB 2: ANALYST INVESTIGATION TRIAGE
# ==========================================
with tab_triage:
    st.subheader("High-Risk Investigation Queue (Pending Action)")
    df_pending = load_pending_alerts()

    if df_pending.empty:
        st.success("🎉 Review queue clear! All alerts have been dispositioned to Delta Lake.")
    else:
        t_sel, t_det = st.columns([1, 2])
        
        with t_sel:
            st.write(f"##### Queue ({len(df_pending)} unreviewed)")
            
            selection_options = df_pending.apply(
                lambda row: f"{row['anomaly_score']:.2f} | Tx: {str(row['transaction_id'])[:8]} | User: {row['user_id']} | ${row['amount']:.2f}",
                axis=1
            ).tolist()
            
            selected_index = st.radio(
                "Select Alert to Triage (Ranked by anomaly):",
                options=range(len(selection_options)),
                format_func=lambda i: selection_options[i]
            )
            
            alert_row = df_pending.iloc[selected_index]

        with t_det:
            st.write(f"##### Case Details: Transaction `{alert_row['transaction_id']}`")
            st.write(f"**Timestamp:** `{alert_row['event_timestamp']}`")
            
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Amount", f"${alert_row['amount']:,.2f}")
            mc2.metric("User Profile", alert_row["segment"])
            mc3.metric("Daily Limit", f"${alert_row['daily_limit']:,.2f}")

            mcl1, mcl2 = st.columns(2)
            mcl1.write(f"**Tx Location:** `{alert_row['location']}`")
            mcl2.write(f"**Account Home:** `{alert_row['home_city']}`")

            st.divider()
            st.write("**Automated Forensic Narrative & SAR Evidence Justification:**")
            st.info(alert_row["sar_narrative"])
            
            st.subheader("Investigator Disposition")
            notes = st.text_input("Analyst Case Notes (Required):", value="Geolocation mismatch confirmed against home profile.")
            
            b1, b2, b3 = st.columns(3)

            with b1:
                if st.button("🚨 Escalate & Freeze Account", use_container_width=True):
                    if record_disposition(alert_row['transaction_id'], alert_row['user_id'], "FREEZE_ACCOUNT", notes):
                        st.error(f"Account for user {alert_row['user_id']} frozen. Audit logged to Delta Lake.")
                        st.rerun()

            with b2:
                if st.button("⚠️ Request Two-Factor Verification", use_container_width=True):
                    if record_disposition(alert_row['transaction_id'], alert_row['user_id'], "REQUEST_2FA", notes):
                        st.warning(f"2FA Challenge dispatched. Audit logged to Delta Lake.")
                        st.rerun()

            with b3:
                if st.button("✅ Mark as False Positive", use_container_width=True):
                    if record_disposition(alert_row['transaction_id'], alert_row['user_id'], "FALSE_POSITIVE", notes):
                        st.success(f"Transaction {alert_row['transaction_id']} dismissed. Audit logged to Delta Lake.")
                        st.rerun()

        st.divider()
        st.subheader("Raw Data Inspector (Pending Queue)")
        st.dataframe(df_pending, use_container_width=True)