package com.deliverex.live

import com.deliverex.live.data.local.OfflineDemoEngine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OfflineDemoEngineTest {
    @Test
    fun `guided step 2 triggers barge-in and creates manager approval`() {
        val engine = OfflineDemoEngine()
        val step1 = engine.runGuidedStep(1)
        assertEquals("RECORD_DELIVERY", step1.intent)

        val step2 = engine.runGuidedStep(2)
        assertTrue(step2.isBargeIn)
        assertTrue(step2.matchedPolicies.contains("SOP-4.2"))
        assertTrue(step2.state.approvals.any { it.status == "PENDING" && it.discountRequested == 500 })
    }

    @Test
    fun `manager 1-tap approve settles invoice and issues official receipt`() {
        val engine = OfflineDemoEngine()
        val step2 = engine.runGuidedStep(2)
        val pendingId = step2.state.approvals.first().approvalId

        val decision = engine.decideApproval(pendingId, "APPROVED")
        assertEquals("APPROVED", decision.decision)
        assertNotNull(decision.receipt)
        val krishna = decision.state.customers.first { it.name == "Krishna Hardware" }
        assertEquals(0, krishna.balanceDue)
        assertEquals("SETTLED", krishna.status)
    }
}
