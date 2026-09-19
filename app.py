from datetime import date
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Personal Finance Command Center", layout="wide")

# Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)


def load_sheet(sheet_name):
    df = conn.read(worksheet=sheet_name, ttl=0)
    if df is not None and not df.empty:
        return df.dropna(how="all")
    return pd.DataFrame()


st.title("💼 Financial Command Center & Daily Tracker")

menu = st.sidebar.radio(
    "Navigation",
    [
        "📊 Overview Dashboard",
        "📝 Daily Data Entry",
        "🤝 Debts & Receivables",
        "📜 Transaction History",
    ],
)

# ---------------------------------------------------------
# 1. OVERVIEW DASHBOARD
# ---------------------------------------------------------
if menu == "📊 Overview Dashboard":
    st.header("Real-Time Liquidity & Net Worth")

    accounts_df = load_sheet("accounts")
    debts_df = load_sheet("debts")

    if not accounts_df.empty and not debts_df.empty:
        accounts_df["balance"] = pd.to_numeric(
            accounts_df["balance"], errors="coerce"
        ).fillna(0)
        debts_df["amount"] = pd.to_numeric(
            debts_df["amount"], errors="coerce"
        ).fillna(0)

        total_bank = accounts_df[accounts_df["type"] == "Bank"][
            "balance"
        ].sum()
        total_trading = accounts_df[accounts_df["type"] == "Trading"][
            "balance"
        ].sum()

        peer_receivables = debts_df[
            debts_df["category"] == "Peer Receivable (Owes You)"
        ]["amount"].sum()
        credit_card_debt = debts_df[
            debts_df["category"] == "Credit Card Debt"
        ]["amount"].sum()
        peer_payables = debts_df[
            debts_df["category"] == "Peer Payable (You Owe)"
        ]["amount"].sum()

        total_assets = total_bank + total_trading + peer_receivables
        total_liabilities = credit_card_debt + peer_payables
        net_worth = total_assets - total_liabilities

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Bank Liquidity", f"₹{total_bank:,.2f}")
        col2.metric("Trading Assets", f"₹{total_trading:,.2f}")
        col3.metric("Total Liabilities", f"₹{total_liabilities:,.2f}")
        col4.metric("Net Liquidity", f"₹{net_worth:,.2f}")

        if total_bank < total_liabilities:
            st.error(
                f"⚠️ **Cash Deficit Alert:** Bank cash (₹{total_bank:,.2f}) is lower than debts (₹{total_liabilities:,.2f}). Shortfall: ₹{total_liabilities - total_bank:,.2f}."
            )

        st.subheader("Account Balances")
        st.dataframe(accounts_df, use_container_width=True)
    else:
        st.warning(
            "Please check your Google Sheet tabs. Accounts or Debts data appears empty."
        )

# ---------------------------------------------------------
# 2. DAILY DATA ENTRY
# ---------------------------------------------------------
elif menu == "📝 Daily Data Entry":
    st.header("Record Daily Activity")

    accounts_df = load_sheet("accounts")
    debts_df = load_sheet("debts")
    logs_df = load_sheet("daily_logs")

    accounts_df["balance"] = pd.to_numeric(
        accounts_df["balance"], errors="coerce"
    ).fillna(0)
    debts_df["amount"] = pd.to_numeric(
        debts_df["amount"], errors="coerce"
    ).fillna(0)

    bank_accounts = accounts_df[accounts_df["type"] == "Bank"][
        "name"
    ].tolist()
    all_accounts = accounts_df["name"].tolist()
    all_debts = debts_df["person_or_card"].tolist()

    with st.form("entry_form"):
        log_date = st.date_input("Date", date.today())
        trans_type = st.selectbox(
            "Transaction Type",
            [
                "Expense (Outflow)",
                "Trading Profit Withdrawal",
                "Peer Debt Settlement",
                "Credit Card Payment",
            ],
        )

        source_target = st.selectbox(
            "Account / Debt Involved", all_accounts + all_debts
        )

        # Secondary account selector for payments/settlements
        selected_bank = st.selectbox(
            "Bank Account Used (For Payments / Received Debt)",
            bank_accounts,
            help="Select which bank account loses or gains money during this transaction.",
        )

        amount = st.number_input("Amount (₹)", min_value=1.0, step=100.0)
        notes = st.text_input("Notes (e.g., Daily Jar Gold, Netflix, SIP)")

        submitted = st.form_submit_button("Submit Entry")

        if submitted:
            # 1. Append Log Entry
            new_log = pd.DataFrame(
                [
                    {
                        "id": len(logs_df) + 1 if not logs_df.empty else 1,
                        "log_date": str(log_date),
                        "type": trans_type,
                        "source_target": source_target,
                        "amount": amount,
                        "notes": notes,
                    }
                ]
            )
            updated_logs = (
                pd.concat([logs_df, new_log], ignore_index=True)
                if not logs_df.empty
                else new_log
            )
            conn.update(worksheet="daily_logs", data=updated_logs)

            # 2. Update Balances & Debts
            if trans_type == "Expense (Outflow)":
                if source_target in all_accounts:
                    idx = accounts_df[
                        accounts_df["name"] == source_target
                    ].index[0]
                    accounts_df.at[idx, "balance"] -= amount
                    conn.update(worksheet="accounts", data=accounts_df)

            elif trans_type == "Trading Profit Withdrawal":
                if source_target in bank_accounts:
                    idx = accounts_df[
                        accounts_df["name"] == source_target
                    ].index[0]
                    accounts_df.at[idx, "balance"] += amount
                    conn.update(worksheet="accounts", data=accounts_df)

            elif trans_type in ["Peer Debt Settlement", "Credit Card Payment"]:
                # Reduce Debt Balance
                if source_target in all_debts:
                    d_idx = debts_df[
                        debts_df["person_or_card"] == source_target
                    ].index[0]
                    debt_cat = debts_df.at[d_idx, "category"]
                    debts_df.at[d_idx, "amount"] = max(
                        0.0, debts_df.at[d_idx, "amount"] - amount
                    )
                    conn.update(worksheet="debts", data=debts_df)

                    # Adjust Bank Balance based on whether money came IN or went OUT
                    b_idx = accounts_df[
                        accounts_df["name"] == selected_bank
                    ].index[0]
                    if debt_cat in [
                        "Credit Card Debt",
                        "Peer Payable (You Owe)",
                    ]:
                        accounts_df.at[
                            b_idx, "balance"
                        ] -= amount  # Paid money out
                    elif debt_cat == "Peer Receivable (Owes You)":
                        accounts_df.at[
                            b_idx, "balance"
                        ] += amount  # Received money in

                    conn.update(worksheet="accounts", data=accounts_df)

            st.success("Transaction recorded and Google Sheets updated!")
            st.rerun()

# ---------------------------------------------------------
# 3. DEBTS & RECEIVABLES
# ---------------------------------------------------------
elif menu == "🤝 Debts & Receivables":
    st.header("Peer Loans & Credit Card Payables")
    debts_df = load_sheet("debts")
    if not debts_df.empty:
        st.dataframe(debts_df, use_container_width=True)

# ---------------------------------------------------------
# 4. TRANSACTION HISTORY
# ---------------------------------------------------------
elif menu == "📜 Transaction History":
    st.header("Daily Activity Logs")
    logs_df = load_sheet("daily_logs")
    if not logs_df.empty:
        st.dataframe(logs_df, use_container_width=True)
