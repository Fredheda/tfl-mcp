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
// This file grows in a later cycle to add the tfl-status-agent's Container
// Apps environment/identity/app/authConfig alongside these resources --
// the same one-file-per-repo pattern copilot-kit-exp's main.bicep uses.

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
