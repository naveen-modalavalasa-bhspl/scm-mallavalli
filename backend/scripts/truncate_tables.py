import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.database import engine

TABLES_TO_TRUNCATE = [
    # Inventory & Ledgers
    "stock_balance", "stock_ledger", "vehicle_stock_balance", "vehicle_stock_ledger",
    "serial_numbers", "batches", "stock_audits", "stock_audit_items",
    
    # Indents & Issues
    "indents", "indent_items", "indent_acknowledgements", "indent_acknowledgement_items",
    "material_issues", "material_issue_items", "vehicle_issues", "vehicle_issue_items",
    "issue_returns", "issue_return_items", "material_acknowledgements", "material_acknowledgement_items",
    
    # Procurement / Inwards
    "material_requests", "material_request_items", "mr_buckets", "mr_indent_links",
    "purchase_orders", "purchase_order_items", "purchase_returns", "purchase_return_items",
    "goods_receipt_notes", "grn_items", "grn_item_serials", "material_inwards", "material_inward_items",
    "putaway_orders", "putaway_items", "quality_inspections", "quality_inspection_items",
    "quotations", "quotation_items", "rfqs", "rfq_items", "rfq_vendors",
    
    # Outbound & Transfers
    "sales_orders", "sales_order_items", "delivery_orders",
    "wave_plans", "wave_plan_orders", "picking_orders", "picking_items", "packing_orders", "packing_items",
    "dispatch_orders", "dispatch_order_items", "dispatch_handovers", "dispatch_delivery_acknowledgements", 
    "dispatch_acknowledgement_items", "dispatch_acknowledgement_documents", "dispatch_custody_transfers",
    "gate_passes", "stock_transfers", "stock_transfer_items",
    "consignments", "consignment_packages", "consignment_package_items", "consignment_package_containers", 
    "consignment_package_acknowledgements", "consignment_parent_packages", "consignment_parent_package_children",
    
    # Logistics
    "logistics_main_dispatch_orders", "logistics_sub_dispatch_orders", "logistics_sdo_destinations",
    "logistics_dispatch_materials", "logistics_rfq_masters", "logistics_rfq_dispatch_mappings",
    "logistics_rfq_vendors", "logistics_rfq_responses", "logistics_rfq_response_vehicles",
    "logistics_rfq_response_sdo_assignments", "logistics_service_orders", "logistics_service_order_vehicles",
    "logistics_service_order_sdo_mappings",
    
    # Approvals / Logs / Others
    "activity_logs", "approval_requests", "approval_history", "approval_delegations",
    "barcode_registry", "business_rule_executions", "cold_chain_logs", "compliance_audits",
    "e_signatures", "email_logs", "file_attachments", "mrp_runs", "mrp_run_items",
    "notifications", "prescription_records", "scan_logs"
]

async def main():
    print("Starting truncation process...")
    async with engine.begin() as conn:
        print("Disabling foreign key checks...")
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        
        for table in TABLES_TO_TRUNCATE:
            print(f"Truncating {table}...")
            try:
                await conn.execute(text(f"TRUNCATE TABLE {table};"))
                print(f" -> Success")
            except Exception as e:
                print(f" -> Failed: {e}")
                
        print("Re-enabling foreign key checks...")
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
