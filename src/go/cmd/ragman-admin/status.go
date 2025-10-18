package main

import (
	"encoding/json"
	"fmt"
	"strings"
)

type OutputFormat string

const (
	FormatText OutputFormat = "text"
	FormatJSON OutputFormat = "json"
)

type ProgressView struct {
	Stage           string  `json:"stage"`
	PercentComplete float64 `json:"percent_complete"`
	RetryCount      int     `json:"retry_count"`
}

type ScheduleView struct {
	Cadence       string `json:"cadence"`
	NextRunAt     string `json:"next_run_at"`
	LastSuccessAt string `json:"last_success_at"`
}

type EvictionView struct {
	TotalEntries        int    `json:"total_entries"`
	TotalBytes          int64  `json:"total_bytes"`
	BudgetBytes         int64  `json:"budget_bytes"`
	LastEvictionAt      string `json:"last_eviction_at"`
	LastEvictionRemoved int    `json:"last_eviction_removed"`
	LastEvictionBytes   int64  `json:"last_eviction_bytes"`
}

type StatusView struct {
	LatestJobID        string   `json:"latest_job_id"`
	LatestJobStatus    string   `json:"latest_job_status"`
	CacheDiskPercent   float64  `json:"cache_disk_pct"`
	CacheHitRate       int      `json:"cache_hit_rate"`
	ActiveModels       []string `json:"active_models"`
	ManPagesProcessed  int      `json:"man_pages_processed"`
	WikiArticlesLoaded int      `json:"wiki_articles_loaded"`
	IngestionErrors    []string `json:"ingestion_errors"`
	Progress           ProgressView
	Schedule           ScheduleView
	Eviction           EvictionView
}

func RenderStatus(view StatusView, format OutputFormat) (string, error) {
	switch format {
	case FormatJSON:
		return renderStatusJSON(view)
	default:
		return renderStatusText(view), nil
	}
}

func renderStatusJSON(view StatusView) (string, error) {
	payload := struct {
		LatestJobID        string       `json:"latest_job_id"`
		LatestJobStatus    string       `json:"latest_job_status"`
		CacheDiskPercent   float64      `json:"cache_disk_pct"`
		CacheHitRate       int          `json:"cache_hit_rate"`
		ActiveModels       []string     `json:"active_models"`
		ManPagesProcessed  int          `json:"man_pages_processed"`
		WikiArticlesLoaded int          `json:"wiki_articles_loaded"`
		IngestionErrors    []string     `json:"ingestion_errors"`
		Progress           ProgressView `json:"progress"`
		Schedule           ScheduleView `json:"schedule"`
		Eviction           EvictionView `json:"eviction"`
	}{
		LatestJobID:        view.LatestJobID,
		LatestJobStatus:    view.LatestJobStatus,
		CacheDiskPercent:   view.CacheDiskPercent,
		CacheHitRate:       view.CacheHitRate,
		ActiveModels:       view.ActiveModels,
		ManPagesProcessed:  view.ManPagesProcessed,
		WikiArticlesLoaded: view.WikiArticlesLoaded,
		IngestionErrors:    view.IngestionErrors,
		Progress:           view.Progress,
		Schedule:           view.Schedule,
		Eviction:           view.Eviction,
	}

	bytes, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return "", err
	}
	return string(bytes) + "\n", nil
}

func renderStatusText(view StatusView) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Latest ingestion job: %s (%s)\n", fallbackString(view.LatestJobID, "unknown"), fallbackString(view.LatestJobStatus, "unknown"))
	fmt.Fprintf(&b, "Progress: %s\n", formatProgress(view.Progress))
	fmt.Fprintf(&b, "Retries: %d\n", max(view.Progress.RetryCount, 0))
	fmt.Fprintf(&b, "Man pages processed: %d\n", view.ManPagesProcessed)
	fmt.Fprintf(&b, "Wiki articles loaded: %d\n", view.WikiArticlesLoaded)
	if len(view.IngestionErrors) == 0 {
		b.WriteString("Errors: none\n")
	} else {
		b.WriteString("Errors:\n")
		for _, item := range view.IngestionErrors {
			fmt.Fprintf(&b, "- %s\n", item)
		}
	}
	b.WriteString("\n")
	b.WriteString("Schedule summary:\n")
	fmt.Fprintf(&b, "  Cadence: %s\n", fallbackString(view.Schedule.Cadence, "unknown"))
	fmt.Fprintf(&b, "  Next run: %s\n", fallbackString(view.Schedule.NextRunAt, "unknown"))
	fmt.Fprintf(&b, "  Last success: %s\n", fallbackString(view.Schedule.LastSuccessAt, "unknown"))
	b.WriteString("\n")
	fmt.Fprintf(&b, "Cache usage: %.1f%% (hit rate: %s)\n", view.CacheDiskPercent, formatHitRate(view.CacheHitRate))
	b.WriteString("Eviction telemetry:\n")
	fmt.Fprintf(&b, "  Total entries: %d\n", view.Eviction.TotalEntries)
	fmt.Fprintf(&b, "  Total size: %s / %s\n", formatBytes(view.Eviction.TotalBytes), formatBytes(view.Eviction.BudgetBytes))
	fmt.Fprintf(&b, "  Last eviction: %s\n", fallbackString(view.Eviction.LastEvictionAt, "n/a"))
	fmt.Fprintf(&b, "  Removed: %d entries (%s)\n", view.Eviction.LastEvictionRemoved, formatBytes(view.Eviction.LastEvictionBytes))
	b.WriteString("\n")
	fmt.Fprintf(&b, "Active models: %s\n", formatList(view.ActiveModels))
	return b.String()
}

func formatProgress(progress ProgressView) string {
	stage := strings.TrimSpace(progress.Stage)
	switch {
	case progress.PercentComplete > 0 && stage != "":
		return fmt.Sprintf("%.1f%% (stage: %s)", progress.PercentComplete, stage)
	case progress.PercentComplete > 0:
		return fmt.Sprintf("%.1f%%", progress.PercentComplete)
	case stage != "":
		return stage
	default:
		return "not started"
	}
}

func formatHitRate(rate int) string {
	if rate < 0 {
		return "unknown"
	}
	return fmt.Sprintf("%d%%", rate)
}

func formatBytes(value int64) string {
	if value <= 0 {
		return "0 B"
	}
	const unit = 1024.0
	sizes := []string{"B", "KiB", "MiB", "GiB", "TiB"}
	fValue := float64(value)
	idx := 0
	for fValue >= unit && idx < len(sizes)-1 {
		fValue /= unit
		idx++
	}
	return fmt.Sprintf("%.1f %s", fValue, sizes[idx])
}

func formatList(values []string) string {
	if len(values) == 0 {
		return "none"
	}
	return strings.Join(values, ", ")
}

func fallbackString(value string, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return fallback
	}
	return value
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
