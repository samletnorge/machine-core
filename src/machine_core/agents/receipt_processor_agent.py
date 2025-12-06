"""Receipt processor agent with vision model."""

from core.agent_base import BaseAgent
from loguru import logger


class ReceiptProcessorAgent(BaseAgent):
    """Receipt processor agent with vision model.
    
    Processes receipts infinitely from a queue, extracts data, updates DB.
    Perfect for: Queue processing, document analysis, data extraction
    """
    
    def __init__(self):
        super().__init__(
            model_name="qwen-vl",  # Vision model for receipt reading
            system_prompt="""You are a receipt analyzer. Extract:
- Store name
- Date
- Items with prices
- Total amount
- Payment method
Return structured JSON.""",
            mcp_config_path="mcp_receipt.json"  # Includes DB tools
        )
        self.db_queue_empty = False
    
    async def run(self):
        """Process receipts from queue until empty."""
        logger.info("Receipt processor started")
        
        while not self.db_queue_empty:
            try:
                # Get next receipt from queue (pseudo-code)
                receipt_path = await self._get_next_receipt()
                
                if not receipt_path:
                    self.db_queue_empty = True
                    break
                
                logger.info(f"Processing receipt: {receipt_path}")
                
                # Process with vision
                result = await self.run_query(
                    "Extract all information from this receipt",
                    image_paths=receipt_path
                )
                
                # Save to DB (pseudo-code)
                await self._save_to_db(result)
                
            except Exception as e:
                logger.error(f"Error processing receipt: {e}")
                # Continue to next receipt
                continue
        
        logger.info("Receipt processor finished")
    
    async def _get_next_receipt(self):
        """Get next receipt from queue (implement with your DB)."""
        # TODO: Implement your queue logic
        pass
    
    async def _save_to_db(self, result):
        """Save extracted data to database."""
        # TODO: Implement your DB logic
        pass
