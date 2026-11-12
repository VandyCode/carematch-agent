output "cloud_run_url" {
  description = "Public HTTPS endpoint for the CareMatch FastAPI + A2A service"
  value       = google_cloud_run_v2_service.carematch_service.uri
}

output "artifact_registry_repository" {
  description = "Docker Artifact Registry repository ID for CareMatch images"
  value       = google_artifact_registry_repository.carematch_repo.repository_id
}

output "secret_manager_secret_id" {
  description = "Secret Manager resource ID storing the Gemini API key"
  value       = google_secret_manager_secret.gemini_api_key.secret_id
}
