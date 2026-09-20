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
        "🍕 Split Bill",
        "🤝 Debts & Receivables",
        "📜 Transaction History",
    ],
)

# ---------------------------------------------------------
# 1. OVERVIEW DASHBOARD
# ---------------------------------------------------------
if menu == "📊 Overview Dashboard":
    st.header("Real-Time Liquidity & Net Worth")

    # Private Mode State Toggle
    if "hide_privacy" not in st.session_state:
        st.session_state.hide_privacy = False

    col_title, col_btn = st.columns([3, 1])
    with col_btn:
        btn_label = (
            "👁️ Show Balances"
            if st.session_state.hide_privacy
            else "🔒 Private Mode"
        )
        if st.button(btn_label):
            st.session_state.hide_privacy = not st.session_state.hide_privacy
            st.rerun()

    def fmt_val(val):
        return "₹••••••" if st.session_state.hide_privacy else f"₹{val:,.2f}"

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
        col1.metric("Bank Liquidity", fmt_val(total_bank))
        col2.metric("Trading Assets", fmt_val(total_trading))
        col3.metric("Total Liabilities", fmt_val(total_liabilities))
        col4.metric("Net Liquidity", fmt_val(net_worth))

        if total_bank < total_liabilities and not st.session_state.hide_privacy:
            st.error(
                f"⚠️ **Cash Deficit Alert:** Bank cash ({fmt_val(total_bank)}) is lower than debts ({fmt_val(total_liabilities)}). Shortfall: {fmt_val(total_liabilities - total_bank)}."
            )

        st.subheader("Account Balances")
        if st.session_state.hide_privacy:
            masked_df = accounts_df.copy()
            masked_df["balance"] = "₹••••••"
            st.dataframe(masked_df, use_container_width=True)
        else:
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

    with st.form("entry_form", clear_on_submit=True):
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
                if source_target in all_debts:
                    d_idx = debts_df[
                        debts_df["person_or_card"] == source_target
                    ].index[0]
                    debt_cat = debts_df.at[d_idx, "category"]
                    curr_amt = float(debts_df.at[d_idx, "amount"])

                    net_balance = curr_amt - amount

                    if net_balance < 0:
                        # Crosses zero -> Flip category automatically
                        if debt_cat == "Peer Payable (You Owe)":
                            debts_df.at[d_idx, "category"] = (
                                "Peer Receivable (Owes You)"
                            )
                        elif debt_cat == "Peer Receivable (Owes You)":
                            debts_df.at[d_idx, "category"] = (
                                "Peer Payable (You Owe)"
                            )
                        debts_df.at[d_idx, "amount"] = abs(net_balance)
                    else:
                        debts_df.at[d_idx, "amount"] = net_balance

                    conn.update(worksheet="debts", data=debts_df)

                    # Adjust Bank Balance
                    b_idx = accounts_df[
                        accounts_df["name"] == selected_bank
                    ].index[0]
                    if debt_cat in [
                        "Credit Card Debt",
                        "Peer Payable (You Owe)",
                    ]:
                        accounts_df.at[b_idx, "balance"] -= amount
                    elif debt_cat == "Peer Receivable (Owes You)":
                        accounts_df.at[b_idx, "balance"] += amount

                    conn.update(worksheet="accounts", data=accounts_df)

            st.success("Transaction recorded and Google Sheets updated!")

# ---------------------------------------------------------
# 3. SPLIT BILL
# ---------------------------------------------------------
elif menu == "🍕 Split Bill":
    st.header("🍕 Split Bill with Friends")

    accounts_df = load_sheet("accounts")
    debts_df = load_sheet("debts")
    logs_df = load_sheet("daily_logs")

    if not accounts_df.empty and not debts_df.empty:
        accounts_df["balance"] = pd.to_numeric(
            accounts_df["balance"], errors="coerce"
        ).fillna(0)
        debts_df["amount"] = pd.to_numeric(
            debts_df["amount"], errors="coerce"
        ).fillna(0)

        bank_accounts = accounts_df[accounts_df["type"] == "Bank"][
            "name"
        ].tolist()
        existing_friends = debts_df[
            debts_df["category"].str.contains("Peer", na=False)
        ]["person_or_card"].tolist()

        with st.form("split_bill_form", clear_on_submit=True):
            bill_date = st.date_input("Date", date.today())
            title = st.text_input(
                "Bill Description / Event",
                placeholder="e.g., Weekend Dinner, Movie",
            )

            col1, col2 = st.columns(2)
            with col1:
                total_amount = st.number_input(
                    "Total Paid Out (₹)", min_value=1.0, step=100.0
                )
            with col2:
                paid_by_bank = st.selectbox(
                    "Paid From Bank Account", bank_accounts
                )

            selected_friends = st.multiselect(
                "Select Friends Involved", existing_friends
            )
            new_friend = st.text_input(
                "Add New Friend (if not listed above)",
                placeholder="e.g., Niket",
            )

            all_participants = selected_friends.copy()
            if new_friend.strip() and new_friend.strip() not in all_participants:
                all_participants.append(new_friend.strip())

            st.markdown("---")
            st.subheader("Split Breakdown")

            split_mode = st.radio(
                "Split Method",
                ["Equal Split", "Custom Amounts"],
                horizontal=True,
            )

            friend_shares = {}
            if all_participants:
                num_people = len(all_participants) + 1
                default_share = (
                    round(total_amount / num_people, 2)
                    if total_amount > 0
                    else 0.0
                )

                if split_mode == "Equal Split":
                    user_share = default_share
                    st.info(
                        f"Each person's share ({num_people} people total): **₹{default_share:,.2f}**"
                    )
                    for friend in all_participants:
                        friend_shares[friend] = default_share
                else:
                    user_share = st.number_input(
                        "Your Share (₹)",
                        min_value=0.0,
                        max_value=float(total_amount),
                        value=0.0,
                    )
                    for friend in all_participants:
                        friend_shares[friend] = st.number_input(
                            f"{friend}'s Share (₹)", min_value=0.0, value=0.0
                        )
            else:
                user_share = total_amount

            submitted = st.form_submit_button("Record Split Bill")

            if submitted:
                sum_shares = user_share + sum(friend_shares.values())

                if (
                    split_mode == "Custom Amounts"
                    and abs(sum_shares - total_amount) > 1.0
                ):
                    st.error(
                        f"Total of individual shares (₹{sum_shares}) must equal the Total Paid Out (₹{total_amount})."
                    )
                else:
                    # 1. Deduct Full Outflow from Bank Account
                    b_idx = accounts_df[
                        accounts_df["name"] == paid_by_bank
                    ].index[0]
                    accounts_df.at[b_idx, "balance"] -= total_amount
                    conn.update(worksheet="accounts", data=accounts_df)

                    new_logs = []
                    log_id = len(logs_df) + 1 if not logs_df.empty else 1

                    # 2. Log Your Personal Share as Expense
                    new_logs.append(
                        {
                            "id": log_id,
                            "log_date": str(bill_date),
                            "type": "Expense (Outflow)",
                            "source_target": paid_by_bank,
                            "amount": user_share,
                            "notes": (
                                f"{title} (My Share)"
                                if title
                                else "Split Bill (My Share)"
                            ),
                        }
                    )
                    log_id += 1

                    # 3. Process Each Friend's Portion
                    for friend, f_amount in friend_shares.items():
                        if f_amount <= 0:
                            continue

                        new_logs.append(
                            {
                                "id": log_id,
                                "log_date": str(bill_date),
                                "type": "Peer Debt Settlement",
                                "source_target": friend,
                                "amount": f_amount,
                                "notes": (
                                    f"Paid on behalf of {friend} for {title}"
                                    if title
                                    else f"Paid on behalf of {friend}"
                                ),
                            }
                        )
                        log_id += 1

                        if friend in debts_df["person_or_card"].values:
                            d_idx = debts_df[
                                debts_df["person_or_card"] == friend
                            ].index[0]
                            category = debts_df.at[d_idx, "category"]
                            curr_amt = float(debts_df.at[d_idx, "amount"])

                            if category == "Peer Receivable (Owes You)":
                                debts_df.at[d_idx, "amount"] = (
                                    curr_amt + f_amount
                                )
                            elif category == "Peer Payable (You Owe)":
                                net_amt = curr_amt - f_amount
                                if net_amt < 0:
                                    debts_df.at[d_idx, "category"] = (
                                        "Peer Receivable (Owes You)"
                                    )
                                    debts_df.at[d_idx, "amount"] = abs(net_amt)
                                else:
                                    debts_df.at[d_idx, "amount"] = net_amt
                        else:
                            new_debt_row = pd.DataFrame(
                                [
                                    {
                                        "person_or_card": friend,
                                        "category": "Peer Receivable (Owes You)",
                                        "amount": f_amount,
                                    }
                                ]
                            )
                            debts_df = pd.concat(
                                [debts_df, new_debt_row], ignore_index=True
                            )

                    conn.update(worksheet="debts", data=debts_df)

                    logs_combined = (
                        pd.concat(
                            [logs_df, pd.DataFrame(new_logs)], ignore_index=True
                        )
                        if not logs_df.empty
                        else pd.DataFrame(new_logs)
                    )
                    conn.update(worksheet="daily_logs", data=logs_combined)

                    st.success(
                        "Split bill successfully recorded and balances updated!"
                    )

# ---------------------------------------------------------
# 4. DEBTS & RECEIVABLES
# ---------------------------------------------------------
elif menu == "🤝 Debts & Receivables":
    st.header("Peer Loans & Credit Card Payables")
    debts_df = load_sheet("debts")
    if not debts_df.empty:
        st.dataframe(debts_df, use_container_width=True)

# ---------------------------------------------------------
# 5. TRANSACTION HISTORY
# ---------------------------------------------------------
elif menu == "📜 Transaction History":
    st.header("Daily Activity Logs")
    logs_df = load_sheet("daily_logs")
    if not logs_df.empty:
        st.dataframe(logs_df, use_container_width=True)
