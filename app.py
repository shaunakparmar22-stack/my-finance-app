from datetime import date
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Personal Finance Command Center", layout="wide")

# Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)


def load_sheet(sheet_name):
    return conn.read(worksheet=sheet_name, ttl=0)


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

if menu == "📊 Overview Dashboard":
    st.header("Real-Time Liquidity & Net Worth")

    accounts_df = load_sheet("accounts")
    debts_df = load_sheet("debts")

    accounts_df["balance"] = pd.to_numeric(accounts_df["balance"])
    debts_df["amount"] = pd.to_numeric(debts_df["amount"])

    total_bank = accounts_df[accounts_df["type"] == "Bank"]["balance"].sum()
    total_trading = accounts_df[accounts_df["type"] == "Trading"][
        "balance"
    ].sum()

    peer_receivables = debts_df[
        debts_df["category"] == "Peer Receivable (Owes You)"
    ]["amount"].sum()
    credit_card_debt = debts_df[debts_df["category"] == "Credit Card Debt"][
        "amount"
    ].sum()
    peer_payables = debts_df[debts_df["category"] == "Peer Payable (You Owe)"][
        "amount"
    ].sum()

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

elif menu == "📝 Daily Data Entry":
    st.header("Record Daily Activity")

    accounts_df = load_sheet("accounts")
    debts_df = load_sheet("debts")
    logs_df = load_sheet("daily_logs")

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

        accounts_list = accounts_df["name"].tolist()
        debts_list = debts_df["person_or_card"].tolist()

        source_target = st.selectbox(
            "Account / Person Involved", accounts_list + debts_list
        )
        amount = st.number_input("Amount (₹)", min_value=1.0, step=100.0)
        notes = st.text_input("Notes (e.g., Daily Jar Gold, Netflix, SIP)")

        submitted = st.form_submit_button("Submit Entry")

        if submitted:
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

            if source_target in accounts_list:
                idx = accounts_df[
                    accounts_df["name"] == source_target
                ].index[0]
                if trans_type == "Expense (Outflow)":
                    accounts_df.at[idx, "balance"] = (
                        float(accounts_df.at[idx, "balance"]) - amount
                    )
                elif trans_type == "Trading Profit Withdrawal":
                    accounts_df.at[idx, "balance"] = (
                        float(accounts_df.at[idx, "balance"]) + amount
                    )
                conn.update(worksheet="accounts", data=accounts_df)
            elif source_target in debts_list:
                idx = debts_df[
                    debts_df["person_or_card"] == source_target
                ].index[0]
                debts_df.at[idx, "amount"] = max(
                    0.0, float(debts_df.at[idx, "amount"]) - amount
                )
                conn.update(worksheet="debts", data=debts_df)

            st.success("Transaction recorded and Google Sheets updated!")

elif menu == "🤝 Debts & Receivables":
    st.header("Peer Loans & Credit Card Payables")
    st.dataframe(load_sheet("debts"), use_container_width=True)

elif menu == "📜 Transaction History":
    st.header("Daily Activity Logs")
    st.dataframe(load_sheet("daily_logs"), use_container_width=True)
