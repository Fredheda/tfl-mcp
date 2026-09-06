// Azure Function App (MCP tool server) for the tfl-mcp project.
//
// Provisions, into the shared rg-chatbot resource group (no dedicated
// resource group per project -- see the workspace's deploying-azure-projects
// skill):
//   - a dedicated storage account for the Function App's deployment package
//     (a Flex Consumption requirement, not general-purpose storage)
//   - a Flex Consumption plan + the Function App itself
//
// No ACR, no managed identity, no Container Apps environment here -- Flex
// Consumption Function Apps deploy from a storage-account blob package via
// `func azure functionapp publish` (scripts/deploy-mcp-tools.sh), not a
// container image. Access control is the Function's system MCP key
// (webhookAuthorizationLevel: "System" in function_app/host.json), not
// network isolation -- see
// docs/tfl-mcp/specs/2026-09-06-tfl-mcp-function-app-design.md.
//
// Also declares the tfl-status-agent's Container Apps environment,
// identity, app, and authConfig further down -- one file per repo.

@description('Region for all resources. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Azure Function App name (MCP tool server).')
param functionAppName string = 'func-tfl-mcp'

@description('Storage account backing the Function App (name must be globally unique, lowercase, no dashes).')
param functionStorageAccountName string = 'sttflmcp'

@secure()
@description('MCP extension system key, fetched post-deploy. Unused by the Function App itself (system keys are Functions-runtime-managed) -- kept only so deploy.sh can detect a first deploy.')
param functionMcpKey string = ''

resource functionStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: functionStorageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource functionDeploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: '${functionStorage.name}/default/deployments'
}

resource functionPlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: '${functionAppName}-plan'
  location: location
  kind: 'functionapp'
  sku: { name: 'FC1', tier: 'FlexConsumption' }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  properties: {
    serverFarmId: functionPlan.id
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${functionStorage.properties.primaryEndpoints.blob}deployments'
          authentication: {
            type: 'StorageAccountConnectionString'
            storageAccountConnectionStringName: 'DEPLOYMENT_STORAGE_CONNECTION_STRING'
          }
        }
      }
      runtime: {
        name: 'python'
        version: '3.13'
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 40
        instanceMemoryMB: 2048
      }
    }
    siteConfig: {
      appSettings: [
        { name: 'AzureWebJobsStorage', value: 'DefaultEndpointsProtocol=https;AccountName=${functionStorage.name};AccountKey=${functionStorage.listKeys().keys[0].value};EndpointSuffix=core.windows.net' }
        { name: 'DEPLOYMENT_STORAGE_CONNECTION_STRING', value: 'DefaultEndpointsProtocol=https;AccountName=${functionStorage.name};AccountKey=${functionStorage.listKeys().keys[0].value};EndpointSuffix=core.windows.net' }
      ]
    }
    httpsOnly: true
  }
}

output functionAppHostname string = functionApp.properties.defaultHostName

// --- tfl-status agent (added in cycle 2) ---
//
// External ingress, its own environment (cae-tfl-status) -- internal
// ingress can't cross Container Apps environments, and this agent must be
// reachable from multiple independent consumers, each in their own
// environment. Access control is Microsoft Entra ID token validation via
// Container Apps' built-in auth (authConfig below), not network isolation
// and not application code -- see
// docs/tfl-mcp/specs/2026-09-06-tfl-status-agent-design.md.

@description('Existing Azure Container Registry name (shared across this workspace).')
param acrName string = 'acrchatbotfredheda'

@description('Container Apps environment for the tfl-status agent.')
param agentEnvironmentName string = 'cae-tfl-status'

@description('tfl-status agent container app name.')
param agentAppName string = 'ca-tfl-status-agent'

@description('User-assigned managed identity used for ACR pulls by the agent.')
param agentIdentityName string = 'id-tfl-status-acrpull'

@description('Image tag to deploy for the agent (e.g. a git commit SHA).')
param agentImageTag string = 'latest'

@secure()
param agentOpenaiApiKey string = ''

@description('The tfl-status-agent-api Entra app registration client ID (from scripts/setup-agent-auth.sh).')
param agentAadClientId string = ''

@description('The tenant ID (from scripts/setup-agent-auth.sh).')
param agentAadTenantId string = ''

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var agentLoginServer = '${acrName}.azurecr.io'

resource agentAcr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource agentIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: agentIdentityName
  location: location
}

resource agentAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(agentAcr.id, agentIdentity.id, acrPullRoleId)
  scope: agentAcr
  properties: {
    principalId: agentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

resource agentEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: agentEnvironmentName
  location: location
  properties: {}
}

resource agentApp 'Microsoft.App/containerApps@2025-01-01' = {
  name: agentAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${agentIdentity.id}': {}
    }
  }
  dependsOn: [
    agentAcrPull
  ]
  properties: {
    environmentId: agentEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8002
        transport: 'auto'
      }
      registries: [
        {
          server: agentLoginServer
          identity: agentIdentity.id
        }
      ]
      secrets: [
        {
          name: 'openai-api-key'
          value: agentOpenaiApiKey
        }
        {
          name: 'function-mcp-key'
          value: functionMcpKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'tfl-status-agent'
          image: '${agentLoginServer}/tfl-status-agent:${agentImageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'OPENAI_API_KEY', secretRef: 'openai-api-key' }
            { name: 'FUNCTION_APP_URL', value: 'https://${functionApp.properties.defaultHostName}' }
            { name: 'FUNCTION_MCP_KEY', secretRef: 'function-mcp-key' }
            // Without this, server.py's PUBLIC_URL falls back to
            // http://localhost:8002 -- the a2a-sdk client uses the agent
            // card's own baked-in url for the real RPC POST (not the host
            // used to fetch the card), so a caller's request would
            // literally try to connect to its own localhost.
            { name: 'TFL_STATUS_AGENT_PUBLIC_URL', value: 'https://${agentAppName}.${agentEnvironment.properties.defaultDomain}' }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

resource agentAuthConfig 'Microsoft.App/containerApps/authConfigs@2025-01-01' = if (!empty(agentAadClientId)) {
  parent: agentApp
  name: 'current'
  properties: {
    // platform.enabled is what actually turns on Easy Auth for this app --
    // identityProviders/globalValidation alone are configured but dormant
    // without it (confirmed live: omitting this let unauthenticated
    // requests through with 200, despite Return401 + a configured provider
    // below).
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'Return401'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: agentAadClientId
          openIdIssuer: 'https://login.microsoftonline.com/${agentAadTenantId}/v2.0'
        }
        validation: {
          // Audience matches scripts/setup-agent-auth.sh's identifier URI,
          // which is api://<appId> -- Entra's identifier-URI security policy
          // rejects an arbitrary string like "api://tfl-status-agent" (must
          // contain a tenant-verified domain, the tenant ID, or the app's
          // own ID). See https://aka.ms/identifier-uri-formatting-error.
          allowedAudiences: [
            'api://${agentAadClientId}'
          ]
        }
      }
    }
  }
}

output agentFqdn string = agentApp.properties.configuration.ingress.fqdn
