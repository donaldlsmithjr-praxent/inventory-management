<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget.label') }}</h3>
        </div>
        <div class="budget-slider">
          <input
            type="range"
            min="0"
            :max="maxBudget"
            step="250"
            v-model.number="budget"
            class="slider"
          />
          <div class="budget-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</div>
        </div>
        <p class="budget-help">{{ t('restocking.budget.helpText') }}</p>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.stats.totalBudget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.stats.estimatedSpend') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ estimatedSpend.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</div>
        </div>
        <div :class="['stat-card', remainingBudget < budget * 0.1 ? 'warning' : 'info']">
          <div class="stat-label">{{ t('restocking.stats.remainingBudget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ remainingBudget.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.stats.itemsSelected') }}</div>
          <div class="stat-value">{{ selectedCount }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations.title') }}</h3>
        </div>

        <div v-if="orderSuccessMessage" class="success-banner">{{ orderSuccessMessage }}</div>
        <div v-if="orderErrorMessage" class="error">{{ orderErrorMessage }}</div>

        <div v-if="recommendations.length === 0" class="no-data">
          {{ t('restocking.recommendations.noData') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.currentDemand') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.recommendedQty') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.estimatedCost') }}</th>
                <th>{{ t('restocking.table.included') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="rec in recommendations"
                :key="rec.item_sku"
                :class="{ 'not-selected': !rec.selected }"
              >
                <td><strong>{{ rec.item_sku }}</strong></td>
                <td>{{ rec.item_name }}</td>
                <td>
                  <span :class="['badge', rec.trend]">
                    {{ t(`trends.${rec.trend}`) }}
                  </span>
                </td>
                <td>{{ rec.current_demand }}</td>
                <td>{{ rec.forecasted_demand }}</td>
                <td>{{ rec.recommended_quantity }}</td>
                <td>{{ currencySymbol }}{{ rec.unit_cost.toLocaleString() }}</td>
                <td>{{ currencySymbol }}{{ rec.estimated_cost.toLocaleString() }}</td>
                <td>
                  <span :class="['badge', rec.selected ? 'success' : 'danger']">
                    {{ rec.selected ? t('restocking.table.included') : '' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="recommendations.length > 0 && selectedCount === 0" class="no-data">
          {{ t('restocking.noItemsSelected') }}
        </div>

        <div class="place-order-row">
          <button
            class="place-order-btn"
            :disabled="selectedCount === 0 || placingOrder"
            @click="placeOrder"
          >
            {{ placingOrder ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const loading = ref(true)
    const error = ref(null)
    const recommendations = ref([])
    const budget = ref(5000)
    const maxBudget = ref(15000)
    const placingOrder = ref(false)
    const orderSuccessMessage = ref(null)
    const orderErrorMessage = ref(null)

    let debounceTimer = null

    const loadRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        const data = await api.getRestockRecommendations(budget.value)
        recommendations.value = data

        const totalCost = data.reduce((sum, rec) => sum + rec.estimated_cost, 0)
        maxBudget.value = Math.max(15000, Math.ceil(totalCost / 1000) * 1000)
      } catch (err) {
        error.value = 'Failed to load restock recommendations: ' + err.message
      } finally {
        loading.value = false
      }
    }

    watch(budget, () => {
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        loadRecommendations()
      }, 300)
    })

    const selectedRecommendations = computed(() => {
      return recommendations.value.filter(rec => rec.selected)
    })

    const selectedCount = computed(() => selectedRecommendations.value.length)

    const estimatedSpend = computed(() => {
      return selectedRecommendations.value.reduce((sum, rec) => sum + rec.estimated_cost, 0)
    })

    const remainingBudget = computed(() => {
      return budget.value - estimatedSpend.value
    })

    const placeOrder = async () => {
      placingOrder.value = true
      orderSuccessMessage.value = null
      orderErrorMessage.value = null
      try {
        await Promise.all(
          selectedRecommendations.value.map(rec =>
            api.createRestockOrder({
              item_sku: rec.item_sku,
              item_name: rec.item_name,
              quantity: rec.recommended_quantity,
              unit_cost: rec.unit_cost,
              trend: rec.trend
            })
          )
        )
        orderSuccessMessage.value = t('restocking.orderSuccess')
      } catch (err) {
        orderErrorMessage.value = t('restocking.orderError') + ': ' + err.message
      } finally {
        placingOrder.value = false
      }
    }

    onMounted(() => loadRecommendations())

    return {
      t,
      loading,
      error,
      recommendations,
      budget,
      maxBudget,
      currencySymbol,
      selectedCount,
      estimatedSpend,
      remainingBudget,
      placingOrder,
      orderSuccessMessage,
      orderErrorMessage,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-slider {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.slider {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
  accent-color: #2563eb;
}

.budget-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 100px;
  text-align: right;
}

.budget-help {
  margin-top: 0.75rem;
  color: #64748b;
  font-size: 0.875rem;
}

.not-selected {
  opacity: 0.55;
}

.no-data {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.938rem;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  font-size: 0.938rem;
}

.place-order-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 1.25rem;
}

.place-order-btn {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.625rem 1.5rem;
  border-radius: 8px;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}
</style>
