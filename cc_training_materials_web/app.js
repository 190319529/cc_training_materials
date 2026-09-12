"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const CLASS_COLORS = [
  "#e5484d",
  "#0e9888",
  "#3478c9",
  "#c47f00",
  "#9b51b6",
  "#147d92",
  "#d05b2d",
  "#667085",
];

const WEATHER_LABELS = {
  sunny: "晴天",
  strong_sun: "大太阳",
  cloudy: "多云",
  overcast: "乌云",
  fog: "雾天",
  rain: "雨天",
  snow: "雪天",
  night: "夜间",
};

const state = {
  dataset: null,
  classes: [{ id: 0, name: "目标" }],
  images: [],
  filteredTotal: 0,
  stats: { total: 0, labeled: 0, unlabeled: 0, pending: 0, reviewed: 0, weather: 0, invalid: 0 },
  filter: "pending",
  search: "",
  sort: "boxes_desc",
  pageLimit: 500,
  currentPath: null,
  currentIndex: -1,
  image: null,
  boxes: [],
  selectedBox: -1,
  currentClass: 0,
  dirty: false,
  mode: "draw",
  reviewed: true,
  loadToken: 0,
  view: { scale: 1, offsetX: 0, offsetY: 0 },
  interaction: null,
  previewFrame: null,
  navigationHistory: [],
  navigationCursor: -1,
  imageListScrollTop: 0,
  browser: { kind: "directory", purpose: "dataset", current: "/hdd", selected: null, choose: null },
  dedup: { path: "", threshold: 90, summary: null, busy: false },
  video: { path: "" },
  job: null,
  jobTimer: null,
  handledJobKey: null,
  trainingPlan: null,
  weatherReview: null,
  weatherReviewFilter: "hard",
  weatherFocusId: null,
  weatherLoadToken: 0,
};

const elements = {
  datasetBadge: $("#datasetBadge"),
  dependencyBadge: $("#dependencyBadge"),
  openDatasetButton: $("#openDatasetButton"),
  newProjectButton: $("#newProjectButton"),
  exportDatasetButton: $("#exportDatasetButton"),
  addSourceButton: $("#addSourceButton"),
  addVideoButton: $("#addVideoButton"),
  datasetPath: $("#datasetPath"),
  sourceList: $("#sourceList"),
  totalCount: $("#totalCount"),
  labeledCount: $("#labeledCount"),
  pendingCount: $("#pendingCount"),
  weatherCount: $("#weatherCount"),
  imageSearch: $("#imageSearch"),
  imageSort: $("#imageSort"),
  imageFilters: $("#imageFilters"),
  imageList: $("#imageList"),
  loadMoreButton: $("#loadMoreButton"),
  previousButton: $("#previousButton"),
  nextButton: $("#nextButton"),
  currentImageName: $("#currentImageName"),
  imagePosition: $("#imagePosition"),
  drawModeButton: $("#drawModeButton"),
  panModeButton: $("#panModeButton"),
  zoomOutButton: $("#zoomOutButton"),
  zoomInButton: $("#zoomInButton"),
  fitButton: $("#fitButton"),
  deleteImageButton: $("#deleteImageButton"),
  saveButton: $("#saveButton"),
  canvasStage: $("#canvasStage"),
  canvas: $("#annotationCanvas"),
  canvasEmpty: $("#canvasEmpty"),
  emptyOpenButton: $("#emptyOpenButton"),
  loadingOverlay: $("#loadingOverlay"),
  imageDimensions: $("#imageDimensions"),
  zoomValue: $("#zoomValue"),
  boxCount: $("#boxCount"),
  dirtyState: $("#dirtyState"),
  rightTabs: $("#rightTabs"),
  classEditor: $("#classEditor"),
  classDefinitions: $("#classDefinitions"),
  addClassButton: $("#addClassButton"),
  saveClassesButton: $("#saveClassesButton"),
  classPicker: $("#classPicker"),
  clearBoxesButton: $("#clearBoxesButton"),
  boxList: $("#boxList"),
  reviewedToggle: $("#reviewedToggle"),
  targetPreviewCount: $("#targetPreviewCount"),
  targetPreviewGrid: $("#targetPreviewGrid"),
  modelPath: $("#modelPath"),
  browseModelButton: $("#browseModelButton"),
  confidenceRange: $("#confidenceRange"),
  confidenceOutput: $("#confidenceOutput"),
  predictionDevice: $("#predictionDevice"),
  predictionClassFilters: $("#predictionClassFilters"),
  predictCurrentButton: $("#predictCurrentButton"),
  predictionScope: $("#predictionScope"),
  overwritePolicy: $("#overwritePolicy"),
  startPredictionButton: $("#startPredictionButton"),
  trainingModelPath: $("#trainingModelPath"),
  trainingScope: $("#trainingScope"),
  trainingDataPlan: $("#trainingDataPlan"),
  browseTrainingModelButton: $("#browseTrainingModelButton"),
  trainingEpochs: $("#trainingEpochs"),
  trainingBatch: $("#trainingBatch"),
  trainingImageSize: $("#trainingImageSize"),
  validationRatio: $("#validationRatio"),
  weatherOptions: $("#weatherOptions"),
  weatherRatio: $("#weatherRatio"),
  weatherRatioOutput: $("#weatherRatioOutput"),
  generateWeatherReviewButton: $("#generateWeatherReviewButton"),
  openWeatherReviewButton: $("#openWeatherReviewButton"),
  weatherReviewStatus: $("#weatherReviewStatus"),
  trainingDevice: $("#trainingDevice"),
  startTrainingButton: $("#startTrainingButton"),
  trainingSummary: $("#trainingSummary"),
  jobBar: $("#jobBar"),
  jobKind: $("#jobKind"),
  jobMessage: $("#jobMessage"),
  jobCounter: $("#jobCounter"),
  jobDetails: $("#jobDetails"),
  jobProgressFill: $("#jobProgressFill"),
  cancelJobButton: $("#cancelJobButton"),
  weatherReviewDialog: $("#weatherReviewDialog"),
  weatherReviewSummary: $("#weatherReviewSummary"),
  weatherReviewSelection: $("#weatherReviewSelection"),
  weatherReviewGallery: $("#weatherReviewGallery"),
  weatherReviewFilters: $("#weatherReviewFilters"),
  showHardWeatherButton: $("#showHardWeatherButton"),
  showAllWeatherButton: $("#showAllWeatherButton"),
  weatherOriginalCanvas: $("#weatherOriginalCanvas"),
  weatherEnhancedCanvas: $("#weatherEnhancedCanvas"),
  weatherEnhancedTitle: $("#weatherEnhancedTitle"),
  weatherFocusedName: $("#weatherFocusedName"),
  weatherGapSummary: $("#weatherGapSummary"),
  approveAllWeatherButton: $("#approveAllWeatherButton"),
  rejectAllWeatherButton: $("#rejectAllWeatherButton"),
  closeWeatherReviewButton: $("#closeWeatherReviewButton"),
  cancelWeatherReviewButton: $("#cancelWeatherReviewButton"),
  confirmWeatherReviewButton: $("#confirmWeatherReviewButton"),
  browserDialog: $("#browserDialog"),
  browserTitle: $("#browserTitle"),
  browserPurpose: $("#browserPurpose"),
  browserParentButton: $("#browserParentButton"),
  browserPathInput: $("#browserPathInput"),
  browserGoButton: $("#browserGoButton"),
  browserEntries: $("#browserEntries"),
  browserSelection: $("#browserSelection"),
  chooseCurrentButton: $("#chooseCurrentButton"),
  newProjectDialog: $("#newProjectDialog"),
  newProjectForm: $("#newProjectForm"),
  newProjectPath: $("#newProjectPath"),
  closeNewProjectButton: $("#closeNewProjectButton"),
  cancelNewProjectButton: $("#cancelNewProjectButton"),
  dedupDialog: $("#dedupDialog"),
  dedupForm: $("#dedupForm"),
  dedupPath: $("#dedupPath"),
  dedupThreshold: $("#dedupThreshold"),
  dedupThresholdOutput: $("#dedupThresholdOutput"),
  dedupStats: $("#dedupStats"),
  dedupTotalCount: $("#dedupTotalCount"),
  dedupDeleteCount: $("#dedupDeleteCount"),
  dedupKeepCount: $("#dedupKeepCount"),
  dedupStatus: $("#dedupStatus"),
  scanDedupButton: $("#scanDedupButton"),
  applyDedupButton: $("#applyDedupButton"),
  directAddButton: $("#directAddButton"),
  stopDedupButton: $("#stopDedupButton"),
  closeDedupButton: $("#closeDedupButton"),
  cancelDedupButton: $("#cancelDedupButton"),
  videoDialog: $("#videoDialog"),
  videoForm: $("#videoForm"),
  videoPath: $("#videoPath"),
  videoInterval: $("#videoInterval"),
  videoStatus: $("#videoStatus"),
  startVideoButton: $("#startVideoButton"),
  closeVideoButton: $("#closeVideoButton"),
  cancelVideoButton: $("#cancelVideoButton"),
  toastRegion: $("#toastRegion"),
};

const context = elements.canvas.getContext("2d");

async function api(path, options = {}) {
  const request = { ...options, headers: { ...(options.headers || {}) } };
  if (request.body && typeof request.body !== "string") {
    request.headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(request.body);
  }
  const response = await fetch(path, request);
  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    payload = await response.json();
  }
  if (!response.ok) {
    const error = new Error(payload?.error || `请求失败 (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function showToast(message, type = "normal", duration = 3600) {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), duration);
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  const value = Math.round(seconds);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainingSeconds = value % 60;
  if (hours) return `${hours}小时${String(minutes).padStart(2, "0")}分`;
  if (minutes) return `${minutes}分${String(remainingSeconds).padStart(2, "0")}秒`;
  return `${remainingSeconds}秒`;
}

function colorForClass(classId) {
  return CLASS_COLORS[Math.abs(Number(classId)) % CLASS_COLORS.length];
}

function className(classId) {
  return state.classes.find((item) => item.id === classId)?.name || `类别 ${classId}`;
}

function setDirty(value) {
  state.dirty = Boolean(value);
  elements.dirtyState.textContent = state.dirty ? "未保存" : "已保存";
  elements.dirtyState.classList.toggle("unsaved", state.dirty);
  updateControlState();
}

function canDiscardChanges() {
  return !state.dirty || window.confirm("当前图片有未保存的修改，确定放弃吗？");
}

function currentWeatherSettings() {
  return {
    model_path: elements.trainingModelPath.value.trim(),
    training_scope: elements.trainingScope.value,
    validation_ratio: Number(elements.validationRatio.value) / 100,
    weather_types: $$("#weatherOptions input:checked").map((input) => input.value),
    weather_ratio: Number(elements.weatherRatio.value) / 100,
    device: elements.trainingDevice.value,
  };
}

function weatherSettingsSignature(settings = currentWeatherSettings()) {
  return JSON.stringify({
    model_path: settings.model_path,
    training_scope: settings.training_scope,
    validation_ratio: Number(settings.validation_ratio),
    weather_types: Array.from(settings.weather_types || []),
    weather_ratio: Number(settings.weather_ratio),
  });
}

function weatherReviewRequired() {
  const settings = currentWeatherSettings();
  return settings.weather_ratio > 0 && settings.weather_types.length > 0;
}

function weatherReviewMatchesCurrent() {
  return Boolean(
    state.weatherReview
    && state.weatherReview.materialization_version === 1
    && state.weatherReview.signature === weatherSettingsSignature()
    && state.weatherReview.confirmed,
  );
}

function updateWeatherReviewStatus() {
  const review = state.weatherReview;
  elements.openWeatherReviewButton.hidden = !review;
  elements.generateWeatherReviewButton.textContent = review ? "重新生成并检测" : "生成并检测素材";
  if (!weatherReviewRequired()) {
    elements.weatherReviewStatus.textContent = "天气增强未启用";
  } else if (!review) {
    elements.weatherReviewStatus.textContent = "尚未生成检测素材";
  } else if (review.signature !== weatherSettingsSignature()) {
    elements.weatherReviewStatus.textContent = "训练或天气参数已变化，需要重新生成";
  } else if (review.analysis_version !== 1 && review.confirmed) {
    elements.weatherReviewStatus.textContent = `旧版已加入数据集 ${review.materialized_count} 张；未做模型差异检测`;
  } else if (review.analysis_version !== 1) {
    elements.weatherReviewStatus.textContent = "旧版素材未做模型差异检测，可人工确认或重新生成";
  } else if (!review.confirmed) {
    elements.weatherReviewStatus.textContent = `待确认：默认保留 ${review.approved.size} / ${review.items.length} 张`;
  } else {
    elements.weatherReviewStatus.textContent = `已审核并加入数据集：${review.materialized_count} / ${review.items.length} 张`;
  }
}

function invalidateWeatherReview() {
  updateWeatherReviewStatus();
  updateControlState();
}

function clearWeatherReview() {
  state.weatherReview = null;
  state.weatherFocusId = null;
  state.weatherLoadToken += 1;
  updateWeatherReviewStatus();
}

function updateControlState() {
  const datasetOpen = Boolean(state.dataset?.open);
  const hasImage = Boolean(state.image && state.currentPath);
  const running = state.job?.status === "running";
  const hasModel = elements.modelPath.value.trim().endsWith(".pt");
  const hasTrainingModel = elements.trainingModelPath.value.trim().endsWith(".pt");
  const position = state.images.findIndex((item) => item.path === state.currentPath);

  elements.addSourceButton.disabled = !datasetOpen || running || state.dedup.busy;
  elements.addVideoButton.disabled = !datasetOpen || running || state.dedup.busy;
  elements.exportDatasetButton.disabled = !datasetOpen || running || state.dedup.busy || state.stats.labeled < 10;
  elements.sourceList.querySelectorAll(".source-remove-button").forEach((button) => {
    button.disabled = running;
  });
  elements.imageSearch.disabled = !datasetOpen;
  elements.imageSort.disabled = !datasetOpen;
  elements.addClassButton.disabled = !datasetOpen || running;
  elements.classEditor.querySelectorAll("input, button").forEach((control) => {
    control.disabled = !datasetOpen || running;
  });
  elements.saveClassesButton.disabled = !datasetOpen || running;
  const hasHistoryPrevious = state.navigationCursor > 0;
  const hasHistoryNext = state.navigationCursor >= 0 && state.navigationCursor < state.navigationHistory.length - 1;
  elements.previousButton.disabled = !hasImage || (!hasHistoryPrevious && position <= 0) || running;
  elements.nextButton.disabled = !hasImage || (!hasHistoryNext && (position < 0 || position >= state.images.length - 1)) || running;
  elements.zoomOutButton.disabled = !hasImage;
  elements.zoomInButton.disabled = !hasImage;
  elements.fitButton.disabled = !hasImage;
  elements.deleteImageButton.disabled = !hasImage || running;
  elements.saveButton.disabled = !hasImage || running;
  elements.clearBoxesButton.disabled = !hasImage || state.boxes.length === 0 || running;
  elements.reviewedToggle.disabled = !hasImage || running;
  elements.predictCurrentButton.disabled = !hasImage || !hasModel || running;
  elements.startPredictionButton.disabled = !datasetOpen || !hasModel || running || state.stats.total === 0;
  const insufficientTrainingData = state.trainingPlan && state.trainingPlan.selected_images < 2;
  const canPrepareWeather = datasetOpen
    && hasTrainingModel
    && !running
    && state.stats.labeled >= 2
    && !insufficientTrainingData
    && weatherReviewRequired();
  elements.generateWeatherReviewButton.disabled = !canPrepareWeather;
  elements.openWeatherReviewButton.disabled = running;
  elements.startTrainingButton.disabled = !datasetOpen
    || !hasTrainingModel
    || running
    || state.stats.labeled < 2
    || insufficientTrainingData
    || (weatherReviewRequired() && !weatherReviewMatchesCurrent());
  updateWeatherReviewStatus();
}

function renderDataset() {
  const datasetOpen = Boolean(state.dataset?.open);
  elements.datasetBadge.textContent = datasetOpen ? "数据集已连接" : "未选择数据集";
  elements.datasetBadge.className = `status-badge ${datasetOpen ? "ok" : "neutral"}`;
  elements.datasetPath.textContent = datasetOpen ? state.dataset.root : "尚未选择";
  elements.datasetPath.title = datasetOpen ? state.dataset.root : "";
  elements.sourceList.replaceChildren();
  const sources = state.dataset?.sources || [];
  if (sources.length === 0 && datasetOpen) {
    const empty = document.createElement("div");
    empty.className = "source-item";
    empty.textContent = "尚未添加图片目录";
    elements.sourceList.append(empty);
  }
  for (const source of sources) {
    const row = document.createElement("div");
    row.className = "source-item";
    row.title = source.path;
    const mark = document.createElement("span");
    mark.className = "source-mark";
    const text = document.createElement("span");
    text.className = "source-path";
    text.textContent = source.id ? `${source.id}  ${source.path}` : source.path;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "source-remove-button";
    remove.title = "从项目移除图片目录";
    remove.setAttribute("aria-label", `移除图片目录 ${source.id || source.path}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => removeImageSource(source));
    row.append(mark, text, remove);
    elements.sourceList.append(row);
  }
  updateControlState();
}

function applyDataset(dataset) {
  const previousClass = state.classes.find((item) => item.id === state.currentClass);
  state.dataset = dataset;
  state.classes = dataset.classes?.length ? dataset.classes : [{ id: 0, name: "目标" }];
  const sameName = previousClass && state.classes.find((item) => item.name === previousClass.name);
  const sameId = state.classes.find((item) => item.id === state.currentClass);
  state.currentClass = sameName?.id ?? sameId?.id ?? state.classes[0].id;
  renderClassEditor();
  renderDataset();
  renderClassControls();
}

function setImageFilter(filter) {
  state.filter = filter;
  $$("#imageFilters button").forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === filter);
  });
}

async function openFirstListedImage() {
  if (state.images.length > 0) {
    await loadImage(state.images[0].path, true);
  } else {
    resetCurrentImage();
  }
}

async function openDefaultPendingImage() {
  setImageFilter("pending");
  await loadImages(true);
  await openFirstListedImage();
}

async function openDataset(path, options = {}) {
  if (!canDiscardChanges()) return;
  try {
    const dataset = await api(options.create ? "/api/dataset/create" : "/api/dataset/open", {
      method: "POST",
      body: { path },
    });
    clearWeatherReview();
    resetCurrentImage();
    applyDataset(dataset);
    localStorage.setItem("cc_training_materials.dataset", dataset.root);
    await openDefaultPendingImage();
    await loadTrainingPlan();
    showToast(options.create ? "项目已创建" : "数据集已打开");
  } catch (error) {
    showToast(error.message, "error", 5200);
  }
}

function sourceBrowserStartPath() {
  const sourcePath = state.dataset?.sources?.[0]?.path;
  if (sourcePath?.includes("/")) {
    return sourcePath.slice(0, sourcePath.lastIndexOf("/")) || "/";
  }
  return state.dataset?.root || "/data";
}

function prepareImageSource(path) {
  state.dedup = { path, threshold: 90, summary: null, busy: false };
  elements.dedupPath.textContent = path;
  elements.dedupPath.title = path;
  elements.dedupThreshold.value = "90";
  elements.dedupThresholdOutput.value = "90%";
  elements.dedupStats.hidden = true;
  elements.dedupStatus.textContent = "尚未扫描";
  elements.scanDedupButton.textContent = "开始扫描";
  elements.applyDedupButton.hidden = true;
  elements.stopDedupButton.hidden = true;
  elements.directAddButton.hidden = false;
  elements.dedupDialog.showModal();
}

function prepareVideo(path) {
  state.video.path = path;
  elements.videoPath.textContent = path;
  elements.videoPath.title = path;
  elements.videoInterval.value = "250";
  elements.videoStatus.textContent = "尚未开始";
  elements.startVideoButton.disabled = false;
  elements.videoDialog.showModal();
}

async function startVideoExtraction(event) {
  event.preventDefault();
  if (!state.video.path || state.job?.status === "running") return;
  const intervalMs = Number(elements.videoInterval.value);
  if (!Number.isInteger(intervalMs) || intervalMs < 10 || intervalMs > 60000) {
    showToast("抽帧间隔必须是 10 到 60000 之间的整数毫秒", "error");
    return;
  }
  elements.startVideoButton.disabled = true;
  elements.videoStatus.textContent = "正在启动抽帧任务...";
  try {
    const job = await api("/api/jobs/video", {
      method: "POST",
      body: { path: state.video.path, interval_ms: intervalMs },
    });
    state.job = job;
    renderJob(job);
    startJobPolling();
    elements.videoDialog.close();
    updateControlState();
  } catch (error) {
    elements.videoStatus.textContent = "启动失败";
    elements.startVideoButton.disabled = false;
    showToast(error.message, "error", 7000);
  }
}

function setDedupBusy(busy, message = "", stoppable = busy) {
  state.dedup.busy = busy;
  elements.dedupThreshold.disabled = busy;
  elements.scanDedupButton.disabled = busy;
  elements.applyDedupButton.disabled = busy;
  elements.directAddButton.disabled = busy;
  elements.stopDedupButton.hidden = !stoppable;
  elements.stopDedupButton.disabled = !stoppable;
  elements.closeDedupButton.disabled = busy;
  elements.cancelDedupButton.disabled = busy;
  if (message) elements.dedupStatus.textContent = message;
  updateControlState();
}

function invalidateDedupScan() {
  state.dedup.threshold = Number(elements.dedupThreshold.value);
  state.dedup.summary = null;
  elements.dedupThresholdOutput.value = `${state.dedup.threshold}%`;
  elements.dedupStats.hidden = true;
  elements.dedupStatus.textContent = "阈值已修改，请重新扫描";
  elements.scanDedupButton.textContent = "开始扫描";
  elements.applyDedupButton.hidden = true;
}

async function scanImageSource(event) {
  event.preventDefault();
  if (!state.dedup.path || state.dedup.busy) return;
  const threshold = Number(elements.dedupThreshold.value);
  state.dedup.threshold = threshold;
  state.dedup.summary = null;
  elements.dedupStats.hidden = true;
  elements.applyDedupButton.hidden = true;
  setDedupBusy(true, "正在扫描相似图片...");
  try {
    const summary = await api("/api/sources/dedup/scan", {
      method: "POST",
      body: { path: state.dedup.path, threshold },
    });
    state.dedup.summary = summary;
    elements.dedupTotalCount.textContent = String(summary.total_images ?? 0);
    elements.dedupDeleteCount.textContent = String(summary.delete_candidates ?? 0);
    elements.dedupKeepCount.textContent = String(summary.kept_images ?? 0);
    elements.dedupStats.hidden = false;
    elements.dedupStatus.textContent = `${threshold}% 及以上视为相似，保留排序靠前的一张`;
    elements.scanDedupButton.textContent = "重新扫描";
    elements.applyDedupButton.hidden = false;
  } catch (error) {
    const stopped = error.status === 409 && /停止/.test(error.message || "");
    elements.dedupStatus.textContent = stopped ? "扫描已停止，可直接添加或重新扫描" : "扫描失败";
    if (!stopped) showToast(error.message, "error", 6200);
  } finally {
    setDedupBusy(false);
  }
}

async function stopImageSourceScan() {
  if (!state.dedup.busy) return;
  elements.dedupStatus.textContent = "正在停止扫描...";
  elements.stopDedupButton.disabled = true;
  try {
    await api("/api/sources/dedup/cancel", { method: "POST", body: {} });
  } catch (error) {
    showToast(error.message, "error", 6200);
  }
}

async function addImageSourceDirect() {
  if (!state.dedup.path || state.dedup.busy) return;
  setDedupBusy(true, "正在直接添加图片目录...", false);
  try {
    const result = await api("/api/sources", {
      method: "POST",
      body: { path: state.dedup.path },
    });
    clearWeatherReview();
    applyDataset(result);
    await loadImages(true);
    await loadTrainingPlan();
    elements.dedupDialog.close();
    showToast(`已直接添加图片目录，共 ${result.added?.image_count || 0} 张`);
  } catch (error) {
    elements.dedupStatus.textContent = "添加失败";
    showToast(error.message, "error", 7000);
  } finally {
    setDedupBusy(false);
  }
}

async function applyImageSourceDedup() {
  const summary = state.dedup.summary;
  if (!summary || state.dedup.busy) return;
  const deleteCount = Number(summary.delete_candidates || 0);
  const confirmed = window.confirm(
    `将永久删除 ${deleteCount} 张相似图片，再把目录添加到当前项目。\n\n删除不经过回收站，是否继续？`,
  );
  if (!confirmed) return;
  setDedupBusy(true, "正在删除相似图片并添加目录...");
  try {
    const result = await api("/api/sources/dedup/apply", {
      method: "POST",
      body: { path: state.dedup.path, threshold: state.dedup.threshold },
    });
    clearWeatherReview();
    applyDataset(result.dataset);
    await loadImages(true);
    await loadTrainingPlan();
    elements.dedupDialog.close();
    const deleted = Number(result.apply?.deleted || 0);
    const added = Number(result.dataset?.added?.image_count || 0);
    showToast(`已删除 ${deleted} 张相似图片，添加 ${added} 张图片`, "warning", 5600);
  } catch (error) {
    elements.dedupStatus.textContent = "删除或添加失败，请重新扫描";
    state.dedup.summary = null;
    elements.applyDedupButton.hidden = true;
    showToast(error.message, "error", 7000);
  } finally {
    setDedupBusy(false);
  }
}

async function removeImageSource(source) {
  if (state.job?.status === "running") return;
  const confirmed = window.confirm(`从当前项目移除图片目录？\n\n${source.path}\n\n原图片、标签和复核记录不会删除。`);
  if (!confirmed || !canDiscardChanges()) return;
  try {
    const dataset = await api("/api/sources/remove", {
      method: "POST",
      body: { source_id: source.id, path: source.path },
    });
    clearWeatherReview();
    resetCurrentImage();
    applyDataset(dataset);
    await openDefaultPendingImage();
    await loadTrainingPlan();
    showToast("图片目录已从项目移除，磁盘文件未删除", "warning", 5200);
  } catch (error) {
    showToast(error.message, "error", 5200);
  }
}

function resetCurrentImage() {
  state.loadToken += 1;
  state.currentPath = null;
  state.currentIndex = -1;
  state.image = null;
  state.boxes = [];
  state.selectedBox = -1;
  state.interaction = null;
  state.navigationHistory = [];
  state.navigationCursor = -1;
  state.imageListScrollTop = 0;
  elements.imageList.scrollTop = 0;
  elements.currentImageName.textContent = "未选择图片";
  elements.imagePosition.textContent = "0 / 0";
  elements.imageDimensions.textContent = "--";
  elements.boxCount.textContent = "0 个框";
  elements.canvasEmpty.hidden = false;
  setDirty(false);
  renderBoxList();
  drawCanvas();
}

async function loadImages(reset = true) {
  if (!state.dataset?.open) return;
  const offset = reset ? 0 : state.images.length;
  try {
    const params = new URLSearchParams({
      filter: state.filter,
      search: state.search,
      sort: state.sort,
      offset: String(offset),
      limit: String(state.pageLimit),
    });
    const payload = await api(`/api/images?${params}`);
    state.images = reset ? payload.items : state.images.concat(payload.items);
    state.filteredTotal = payload.filtered;
    state.stats = payload.stats;
    renderImageList();
    renderStats();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderStats() {
  elements.totalCount.textContent = state.stats.total;
  elements.labeledCount.textContent = state.stats.labeled;
  elements.pendingCount.textContent = state.stats.pending;
  elements.weatherCount.textContent = state.stats.weather || 0;
  updateControlState();
}

function imageStatus(entry) {
  if (entry.invalid) return { className: "invalid", label: "标签异常" };
  if (entry.pending) return { className: "pending", label: "待复核" };
  if (entry.reviewed) return { className: "reviewed", label: "已复核" };
  if (entry.has_label) return { className: "labeled", label: "已标注" };
  return { className: "", label: "未标注" };
}

function renderImageList() {
  const rememberedScrollTop = elements.imageList.scrollTop || state.imageListScrollTop;
  elements.imageList.replaceChildren();
  if (state.images.length === 0) {
    const empty = document.createElement("div");
    empty.className = "list-empty";
    empty.textContent = state.dataset?.sources?.length ? "当前筛选没有图片" : "请添加图片目录";
    elements.imageList.append(empty);
  }

  for (const entry of state.images) {
    const status = imageStatus(entry);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `image-item ${entry.path === state.currentPath ? "active" : ""}`;
    button.dataset.path = entry.path;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(entry.path === state.currentPath));
    button.title = entry.path;

    const dot = document.createElement("span");
    dot.className = `image-status-dot ${status.className}`;
    dot.title = status.label;

    const thumbnail = document.createElement("img");
    thumbnail.className = "image-thumb";
    thumbnail.loading = "lazy";
    thumbnail.decoding = "async";
    thumbnail.alt = "";
    thumbnail.src = `/api/image?path=${encodeURIComponent(entry.path)}`;
    thumbnail.addEventListener("error", () => {
      thumbnail.classList.add("image-thumb-error");
    }, { once: true });

    const nameWrap = document.createElement("span");
    nameWrap.className = "image-name";
    const name = document.createElement("strong");
    name.textContent = entry.name;
    const detail = document.createElement("span");
    const parent = entry.path.includes("/") ? entry.path.slice(0, entry.path.lastIndexOf("/")) : status.label;
    const weather = entry.is_weather ? `天气增强 · ${WEATHER_LABELS[entry.weather_type] || entry.weather_type}` : "";
    const location = entry.path.includes("/") ? parent : "";
    detail.textContent = [weather, location, status.label].filter(Boolean).join(" · ");
    nameWrap.append(name, detail);

    const total = document.createElement("span");
    total.className = "box-total";
    total.textContent = entry.has_label ? String(entry.box_count) : "--";
    button.append(thumbnail, dot, nameWrap, total);
    button.addEventListener("click", () => loadImage(entry.path));
    elements.imageList.append(button);
  }
  elements.imageList.scrollTop = rememberedScrollTop;
  const active = elements.imageList.querySelector(".image-item.active");
  if (active) {
    const listRect = elements.imageList.getBoundingClientRect();
    const activeRect = active.getBoundingClientRect();
    if (activeRect.top < listRect.top) {
      elements.imageList.scrollTop -= listRect.top - activeRect.top;
    } else if (activeRect.bottom > listRect.bottom) {
      elements.imageList.scrollTop += activeRect.bottom - listRect.bottom;
    }
  }
  state.imageListScrollTop = elements.imageList.scrollTop;
  elements.loadMoreButton.hidden = state.images.length >= state.filteredTotal;
  updateImagePosition();
}

function updateImagePosition() {
  state.currentIndex = state.images.findIndex((item) => item.path === state.currentPath);
  elements.imagePosition.textContent = state.currentIndex >= 0
    ? `${state.currentIndex + 1} / ${state.filteredTotal}`
    : `0 / ${state.filteredTotal}`;
  updateControlState();
}

async function navigateImage(offset) {
  if (!state.currentPath || state.job?.status === "running") return;
  while (true) {
    const historyIndex = state.navigationCursor + offset;
    if (historyIndex < 0 || historyIndex >= state.navigationHistory.length) break;
    const loaded = await loadImage(state.navigationHistory[historyIndex], false, false, true);
    if (loaded === true) {
      state.navigationCursor = historyIndex;
      updateControlState();
      return;
    }
    if (loaded !== "missing") return;
    state.navigationHistory.splice(historyIndex, 1);
    if (historyIndex < state.navigationCursor) state.navigationCursor -= 1;
  }
  updateControlState();
  const index = state.images.findIndex((item) => item.path === state.currentPath);
  const target = state.images[index + offset];
  if (target) await loadImage(target.path);
}

function removeFromNavigationHistory(path) {
  const removedBeforeOrAtCursor = state.navigationHistory
    .slice(0, state.navigationCursor + 1)
    .filter((item) => item === path).length;
  state.navigationHistory = state.navigationHistory.filter((item) => item !== path);
  state.navigationCursor = Math.max(-1, state.navigationCursor - removedBeforeOrAtCursor);
}

function loadBrowserImage(path) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片加载失败"));
    image.src = `/api/image?path=${encodeURIComponent(path)}`;
  });
}

function normalizedToPixel(box, image) {
  return {
    cls_id: Number(box.cls_id),
    x1: (Number(box.xc) - Number(box.w) / 2) * image.naturalWidth,
    y1: (Number(box.yc) - Number(box.h) / 2) * image.naturalHeight,
    x2: (Number(box.xc) + Number(box.w) / 2) * image.naturalWidth,
    y2: (Number(box.yc) + Number(box.h) / 2) * image.naturalHeight,
  };
}

function pixelToNormalized(box) {
  const width = state.image.naturalWidth;
  const height = state.image.naturalHeight;
  return {
    cls_id: box.cls_id,
    xc: ((box.x1 + box.x2) / 2) / width,
    yc: ((box.y1 + box.y2) / 2) / height,
    w: (box.x2 - box.x1) / width,
    h: (box.y2 - box.y1) / height,
  };
}

async function loadImage(path, force = false, recordHistory = true, silentMissing = false) {
  if (!force && path === state.currentPath) return false;
  if (!force && !canDiscardChanges()) return false;
  const token = ++state.loadToken;
  elements.loadingOverlay.hidden = false;
  try {
    let labelPayload;
    let image;
    if (silentMissing) {
      labelPayload = await api(`/api/labels?image=${encodeURIComponent(path)}`);
      image = await loadBrowserImage(path);
    } else {
      [labelPayload, image] = await Promise.all([
        api(`/api/labels?image=${encodeURIComponent(path)}`),
        loadBrowserImage(path),
      ]);
    }
    if (token !== state.loadToken) return false;
    state.currentPath = path;
    state.image = image;
    state.boxes = labelPayload.boxes.map((box) => normalizedToPixel(box, image));
    state.selectedBox = -1;
    state.reviewed = Boolean(labelPayload.entry.reviewed);
    elements.reviewedToggle.checked = true;
    elements.currentImageName.textContent = path.split("/").pop();
    elements.currentImageName.title = path;
    elements.imageDimensions.textContent = `${image.naturalWidth} x ${image.naturalHeight}`;
    elements.canvasEmpty.hidden = true;
    fitImage();
    setDirty(false);
    renderBoxList();
    renderImageList();
    if (recordHistory) {
      const currentHistoryPath = state.navigationHistory[state.navigationCursor];
      if (currentHistoryPath !== path) {
        state.navigationHistory = state.navigationHistory.slice(0, state.navigationCursor + 1);
        state.navigationHistory.push(path);
        if (state.navigationHistory.length > 200) state.navigationHistory.shift();
        state.navigationCursor = state.navigationHistory.length - 1;
      }
      updateControlState();
    }
    if (labelPayload.warnings.length) {
      showToast(labelPayload.warnings.join("；"), "warning", 6000);
    }
    return true;
  } catch (error) {
    if (error.status === 404) {
      if (!silentMissing) showToast("图片已被移出，自动跳过", "warning");
      return "missing";
    }
    showToast(error.message, "error");
    return false;
  } finally {
    if (token === state.loadToken) elements.loadingOverlay.hidden = true;
  }
}

async function saveLabels() {
  if (!state.currentPath || !state.image) return;
  const currentIndex = state.images.findIndex((item) => item.path === state.currentPath);
  const preferredNext = currentIndex >= 0 ? state.images[currentIndex + 1]?.path : null;
  try {
    const payload = await api("/api/labels", {
      method: "POST",
      body: {
        image: state.currentPath,
        boxes: state.boxes.map(pixelToNormalized),
        reviewed: elements.reviewedToggle.checked,
      },
    });
    clearWeatherReview();
    state.reviewed = payload.entry.reviewed;
    setDirty(false);
    await loadImages(true);
    showToast("标签已保存");
    let nextPath = preferredNext && state.images.some((item) => item.path === preferredNext)
      ? preferredNext
      : null;
    if (!nextPath) {
      const refreshedIndex = state.images.findIndex((item) => item.path === state.currentPath);
      if (refreshedIndex >= 0) nextPath = state.images[refreshedIndex + 1]?.path || null;
      else if (currentIndex >= 0 && currentIndex < state.images.length) nextPath = state.images[currentIndex].path;
    }
    if (nextPath && nextPath !== state.currentPath) await loadImage(nextPath, true);
  } catch (error) {
    showToast(error.message, "error", 5200);
  }
}

async function deleteCurrentImage() {
  if (!state.currentPath || state.job?.status === "running") return;
  const deletedPath = state.currentPath;
  const currentIndex = state.images.findIndex((item) => item.path === deletedPath);
  const preferredNext = currentIndex >= 0 ? state.images[currentIndex + 1]?.path : null;
  try {
    const result = await api("/api/images/delete", {
      method: "POST",
      body: { image: deletedPath },
    });
    clearWeatherReview();
    removeFromNavigationHistory(deletedPath);
    setDirty(false);
    await loadImages(true);
    let nextPath = preferredNext && state.images.some((item) => item.path === preferredNext)
      ? preferredNext
      : null;
    if (!nextPath && state.images.length) {
      nextPath = state.images[Math.min(Math.max(currentIndex, 0), state.images.length - 1)].path;
    }
    if (nextPath) await loadImage(nextPath, true);
    else resetCurrentImage();
    showToast(`图片已移入回收目录：${result.trash_dir}`, "warning", 6000);
  } catch (error) {
    showToast(error.message, "error", 5200);
  }
}

function syncClassDefinitionsCache() {
  const rows = Array.from(elements.classEditor.querySelectorAll(".class-editor-row"));
  elements.classDefinitions.value = rows.map((row) => {
    const id = row.querySelector(".class-id-input")?.value.trim() || "";
    const name = row.querySelector(".class-name-input")?.value.trim() || "";
    return `${id}:${name}`;
  }).join("\n");
}

function appendClassEditorRow(item) {
  const row = document.createElement("div");
  row.className = "class-editor-row";

  const idInput = document.createElement("input");
  idInput.className = "class-id-input";
  idInput.type = "number";
  idInput.min = "0";
  idInput.step = "1";
  idInput.value = String(item.id);
  idInput.setAttribute("aria-label", "类别编号");

  const nameInput = document.createElement("input");
  nameInput.className = "class-name-input";
  nameInput.type = "text";
  nameInput.value = item.name;
  nameInput.placeholder = "例如：无人机";
  nameInput.setAttribute("aria-label", "类别名称");

  const removeButton = document.createElement("button");
  removeButton.className = "icon-button class-remove-button";
  removeButton.type = "button";
  removeButton.title = "删除类别";
  removeButton.setAttribute("aria-label", `删除类别 ${item.name}`);
  removeButton.innerHTML = "&times;";
  removeButton.addEventListener("click", () => {
    row.remove();
    Array.from(elements.classEditor.querySelectorAll(".class-id-input"))
      .forEach((input, index) => { input.value = String(index); });
    syncClassDefinitionsCache();
    updateControlState();
  });

  idInput.addEventListener("input", syncClassDefinitionsCache);
  nameInput.addEventListener("input", syncClassDefinitionsCache);
  row.append(idInput, nameInput, removeButton);
  elements.classEditor.append(row);
}

function renderClassEditor() {
  elements.classEditor.replaceChildren();
  for (const item of state.classes) appendClassEditorRow(item);
  syncClassDefinitionsCache();
  updateControlState();
}

function addClassEditorRow() {
  const ids = Array.from(elements.classEditor.querySelectorAll(".class-id-input"))
    .map((input) => Number(input.value))
    .filter((value) => Number.isInteger(value) && value >= 0);
  const nextId = ids.length ? Math.max(...ids) + 1 : 0;
  appendClassEditorRow({ id: nextId, name: "新类别" });
  syncClassDefinitionsCache();
  const rows = elements.classEditor.querySelectorAll(".class-editor-row");
  rows[rows.length - 1]?.querySelector(".class-name-input")?.select();
  updateControlState();
}

function parseClassDefinitions() {
  const values = [];
  const seen = new Set();
  const rows = Array.from(elements.classEditor.querySelectorAll(".class-editor-row"));
  const definitions = rows.length
    ? rows.map((row) => ({
      idText: row.querySelector(".class-id-input")?.value.trim() || "",
      name: row.querySelector(".class-name-input")?.value.trim() || "",
    }))
    : elements.classDefinitions.value.split(/\r?\n/).filter((line) => line.trim()).map((line) => {
      const separator = line.indexOf(":");
      return {
        idText: separator >= 0 ? line.slice(0, separator).trim() : "",
        name: separator >= 0 ? line.slice(separator + 1).trim() : "",
      };
    });
  for (const [index, definition] of definitions.entries()) {
    const idText = definition.idText;
    const name = definition.name;
    const id = Number(idText);
    if (!Number.isInteger(id) || id < 0 || !name) throw new Error(`第 ${index + 1} 行无效`);
    if (seen.has(id)) throw new Error(`类别 ID ${id} 重复`);
    seen.add(id);
    values.push({ id, name });
  }
  if (!values.length) throw new Error("至少需要一个类别");
  values.sort((a, b) => a.id - b.id);
  values.forEach((item, index) => {
    if (item.id !== index) throw new Error("类别 ID 必须从 0 开始连续排列");
  });
  return values;
}

async function saveClasses() {
  if (!canDiscardChanges()) return;
  try {
    const classes = parseClassDefinitions();
    const currentPath = state.currentPath;
    const dataset = await api("/api/classes", { method: "POST", body: { classes } });
    clearWeatherReview();
    applyDataset(dataset);
    if (currentPath) await loadImage(currentPath, true, false);
    else {
      renderBoxList();
      drawCanvas();
    }
    showToast("类别配置已保存");
  } catch (error) {
    showToast(error.message, "error", 5000);
  }
}

function renderClassControls() {
  elements.classPicker.replaceChildren();
  elements.predictionClassFilters.replaceChildren();
  for (const item of state.classes) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `class-option ${item.id === state.currentClass ? "active" : ""}`;
    const swatch = document.createElement("span");
    swatch.className = "class-swatch";
    swatch.style.background = colorForClass(item.id);
    const name = document.createElement("span");
    name.textContent = item.name;
    const id = document.createElement("span");
    id.className = "class-id";
    id.textContent = String(item.id);
    button.append(swatch, name, id);
    button.addEventListener("click", () => {
      state.currentClass = item.id;
      renderClassControls();
    });
    elements.classPicker.append(button);

    const label = document.createElement("label");
    label.className = "check-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = String(item.id);
    checkbox.checked = true;
    const filterSwatch = swatch.cloneNode();
    const filterName = document.createElement("span");
    filterName.textContent = `${item.id}: ${item.name}`;
    label.append(checkbox, filterSwatch, filterName);
    elements.predictionClassFilters.append(label);
  }
}

function renderBoxList() {
  elements.boxList.replaceChildren();
  elements.boxCount.textContent = `${state.boxes.length} 个框`;
  if (!state.boxes.length) {
    const empty = document.createElement("div");
    empty.className = "list-empty compact-empty";
    empty.textContent = "没有标注框";
    elements.boxList.append(empty);
  }
  state.boxes.forEach((box, index) => {
    const row = document.createElement("div");
    row.className = `box-row ${state.selectedBox === index ? "active" : ""}`;
    const swatch = document.createElement("span");
    swatch.className = "class-swatch";
    swatch.style.background = colorForClass(box.cls_id);
    const select = document.createElement("select");
    select.setAttribute("aria-label", `标注框 ${index + 1} 类别`);
    for (const item of state.classes) {
      const option = document.createElement("option");
      option.value = String(item.id);
      option.textContent = `${index + 1}. ${item.name}`;
      option.selected = item.id === box.cls_id;
      select.append(option);
    }
    select.addEventListener("change", () => {
      box.cls_id = Number(select.value);
      setDirty(true);
      renderBoxList();
      drawCanvas();
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "icon-button";
    remove.title = "删除标注框";
    remove.setAttribute("aria-label", "删除标注框");
    remove.innerHTML = "&times;";
    remove.addEventListener("click", () => removeBox(index));
    row.addEventListener("click", (event) => {
      if (event.target === select || event.target === remove) return;
      state.selectedBox = index;
      renderBoxList();
      drawCanvas();
    });
    row.append(swatch, select, remove);
    elements.boxList.append(row);
  });
  renderTargetPreviews();
  updateControlState();
}

function targetCrop(box, aspect) {
  const imageWidth = state.image.naturalWidth;
  const imageHeight = state.image.naturalHeight;
  const boxWidth = Math.max(1, box.x2 - box.x1);
  const boxHeight = Math.max(1, box.y2 - box.y1);
  const centerX = (box.x1 + box.x2) / 2;
  const centerY = (box.y1 + box.y2) / 2;
  const base = Math.max(8, boxWidth, boxHeight);
  let width = Math.max(boxWidth * 2.4, boxHeight * 2.4 * aspect, base * 2.4);
  let height = width / aspect;
  if (height < boxHeight * 2.4) {
    height = boxHeight * 2.4;
    width = height * aspect;
  }
  if (width > imageWidth) {
    width = imageWidth;
    height = width / aspect;
  }
  if (height > imageHeight) {
    height = imageHeight;
    width = height * aspect;
  }
  return {
    x: Math.max(0, Math.min(imageWidth - width, centerX - width / 2)),
    y: Math.max(0, Math.min(imageHeight - height, centerY - height / 2)),
    width,
    height,
  };
}

function focusTarget(index) {
  const box = state.boxes[index];
  if (!box || !state.image) return;
  const { width, height } = canvasSize();
  const boxWidth = Math.max(1, box.x2 - box.x1);
  const boxHeight = Math.max(1, box.y2 - box.y1);
  const scale = Math.min(32, width / (boxWidth * 3), height / (boxHeight * 3));
  state.view.scale = Math.max(fittedImageScale(), scale);
  state.view.offsetX = width / 2 - ((box.x1 + box.x2) / 2) * state.view.scale;
  state.view.offsetY = height / 2 - ((box.y1 + box.y2) / 2) * state.view.scale;
  drawCanvas();
}

function renderTargetPreviews() {
  elements.targetPreviewGrid.replaceChildren();
  elements.targetPreviewCount.textContent = `${state.boxes.length} 个目标`;
  if (!state.image || state.boxes.length === 0) {
    const empty = document.createElement("div");
    empty.className = "target-preview-empty";
    empty.textContent = "没有目标框";
    elements.targetPreviewGrid.append(empty);
    return;
  }

  const canvasWidth = 300;
  const canvasHeight = 190;
  const aspect = canvasWidth / canvasHeight;
  state.boxes.forEach((box, index) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `target-preview-card ${state.selectedBox === index ? "active" : ""}`;
    card.title = `${index + 1}. ${className(box.cls_id)}`;

    const preview = document.createElement("canvas");
    preview.width = canvasWidth;
    preview.height = canvasHeight;
    const previewContext = preview.getContext("2d");
    const crop = targetCrop(box, aspect);
    previewContext.fillStyle = "#22282c";
    previewContext.fillRect(0, 0, canvasWidth, canvasHeight);
    previewContext.imageSmoothingEnabled = true;
    previewContext.imageSmoothingQuality = "high";
    previewContext.drawImage(
      state.image,
      crop.x,
      crop.y,
      crop.width,
      crop.height,
      0,
      0,
      canvasWidth,
      canvasHeight,
    );
    const outlineX = (box.x1 - crop.x) / crop.width * canvasWidth;
    const outlineY = (box.y1 - crop.y) / crop.height * canvasHeight;
    const outlineWidth = (box.x2 - box.x1) / crop.width * canvasWidth;
    const outlineHeight = (box.y2 - box.y1) / crop.height * canvasHeight;
    previewContext.strokeStyle = colorForClass(box.cls_id);
    previewContext.lineWidth = 4;
    previewContext.strokeRect(outlineX, outlineY, outlineWidth, outlineHeight);

    const meta = document.createElement("span");
    meta.className = "target-preview-meta";
    const name = document.createElement("strong");
    name.textContent = `${index + 1}. ${className(box.cls_id)}`;
    const size = document.createElement("span");
    size.textContent = `${Math.round(box.x2 - box.x1)} x ${Math.round(box.y2 - box.y1)}`;
    meta.append(name, size);
    card.append(preview, meta);
    card.addEventListener("click", () => {
      state.selectedBox = index;
      renderBoxList();
      focusTarget(index);
    });
    elements.targetPreviewGrid.append(card);
  });
}

function scheduleTargetPreviews() {
  if (state.previewFrame !== null) return;
  state.previewFrame = window.requestAnimationFrame(() => {
    state.previewFrame = null;
    renderTargetPreviews();
  });
}

function removeBox(index) {
  if (index < 0 || index >= state.boxes.length) return;
  state.boxes.splice(index, 1);
  if (state.selectedBox === index) state.selectedBox = -1;
  else if (state.selectedBox > index) state.selectedBox -= 1;
  setDirty(true);
  renderBoxList();
  drawCanvas();
}

function clearBoxes() {
  if (!state.boxes.length) return;
  if (!window.confirm("确定清空当前图片的全部标注框吗？")) return;
  state.boxes = [];
  state.selectedBox = -1;
  setDirty(true);
  renderBoxList();
  drawCanvas();
}

function resizeCanvas() {
  const rect = elements.canvasStage.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  if (elements.canvas.width !== Math.round(width * dpr) || elements.canvas.height !== Math.round(height * dpr)) {
    elements.canvas.width = Math.round(width * dpr);
    elements.canvas.height = Math.round(height * dpr);
    elements.canvas.style.width = `${width}px`;
    elements.canvas.style.height = `${height}px`;
    if (state.image) fitImage();
    else drawCanvas();
  }
}

function canvasSize() {
  return { width: elements.canvas.clientWidth, height: elements.canvas.clientHeight };
}

function fittedImageScale() {
  if (!state.image) return 1;
  const { width, height } = canvasSize();
  return Math.max(0.005, Math.min(width / state.image.naturalWidth, height / state.image.naturalHeight));
}

function fitImage() {
  if (!state.image) return;
  const { width, height } = canvasSize();
  state.view.scale = fittedImageScale();
  state.view.offsetX = (width - state.image.naturalWidth * state.view.scale) / 2;
  state.view.offsetY = (height - state.image.naturalHeight * state.view.scale) / 2;
  drawCanvas();
}

function imageToScreen(x, y) {
  return {
    x: x * state.view.scale + state.view.offsetX,
    y: y * state.view.scale + state.view.offsetY,
  };
}

function screenToImage(x, y, clamp = false) {
  let imageX = (x - state.view.offsetX) / state.view.scale;
  let imageY = (y - state.view.offsetY) / state.view.scale;
  if (clamp && state.image) {
    imageX = Math.max(0, Math.min(state.image.naturalWidth, imageX));
    imageY = Math.max(0, Math.min(state.image.naturalHeight, imageY));
  }
  return { x: imageX, y: imageY };
}

function screenBox(box) {
  const first = imageToScreen(box.x1, box.y1);
  const second = imageToScreen(box.x2, box.y2);
  return { x1: first.x, y1: first.y, x2: second.x, y2: second.y };
}

function drawCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const { width, height } = canvasSize();
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#d7e0e2";
  context.fillRect(0, 0, width, height);
  if (!state.image) return;

  const imageWidth = state.image.naturalWidth * state.view.scale;
  const imageHeight = state.image.naturalHeight * state.view.scale;
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(state.image, state.view.offsetX, state.view.offsetY, imageWidth, imageHeight);

  state.boxes.forEach((box, index) => drawBox(box, index, index === state.selectedBox));
  if (state.interaction?.type === "draw") {
    const start = imageToScreen(state.interaction.start.x, state.interaction.start.y);
    const end = imageToScreen(state.interaction.current.x, state.interaction.current.y);
    context.save();
    context.strokeStyle = "#ffd166";
    context.lineWidth = 2;
    context.setLineDash([7, 5]);
    context.strokeRect(start.x, start.y, end.x - start.x, end.y - start.y);
    context.restore();
  }
  elements.zoomValue.textContent = `${Math.round(state.view.scale * 100)}%`;
}

function drawBox(box, index, selected) {
  const rect = screenBox(box);
  const color = colorForClass(box.cls_id);
  const width = rect.x2 - rect.x1;
  const height = rect.y2 - rect.y1;
  context.save();
  context.strokeStyle = color;
  context.lineWidth = selected ? 3 : 2;
  context.strokeRect(rect.x1, rect.y1, width, height);

  const label = `${box.cls_id}  ${className(box.cls_id)}`;
  context.font = "600 12px sans-serif";
  const labelWidth = Math.ceil(context.measureText(label).width) + 12;
  const labelY = Math.max(0, rect.y1 - 22);
  context.fillStyle = color;
  context.fillRect(rect.x1, labelY, labelWidth, 22);
  context.fillStyle = "#fff";
  context.textBaseline = "middle";
  context.fillText(label, rect.x1 + 6, labelY + 11);

  if (selected) {
    context.fillStyle = "#fff";
    context.strokeStyle = color;
    context.lineWidth = 2;
    for (const point of handlePoints(rect)) {
      context.fillRect(point.x - 4, point.y - 4, 8, 8);
      context.strokeRect(point.x - 4, point.y - 4, 8, 8);
    }
  }
  context.restore();
}

function handlePoints(rect) {
  const middleX = (rect.x1 + rect.x2) / 2;
  const middleY = (rect.y1 + rect.y2) / 2;
  return [
    { name: "nw", x: rect.x1, y: rect.y1 },
    { name: "n", x: middleX, y: rect.y1 },
    { name: "ne", x: rect.x2, y: rect.y1 },
    { name: "e", x: rect.x2, y: middleY },
    { name: "se", x: rect.x2, y: rect.y2 },
    { name: "s", x: middleX, y: rect.y2 },
    { name: "sw", x: rect.x1, y: rect.y2 },
    { name: "w", x: rect.x1, y: middleY },
  ];
}

function canvasPoint(event) {
  const rect = elements.canvas.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function hitHandle(point) {
  if (state.selectedBox < 0 || !state.boxes[state.selectedBox]) return null;
  const rect = screenBox(state.boxes[state.selectedBox]);
  return handlePoints(rect).find((handle) => Math.hypot(point.x - handle.x, point.y - handle.y) <= 8) || null;
}

function hitBox(point) {
  for (let index = state.boxes.length - 1; index >= 0; index -= 1) {
    const rect = screenBox(state.boxes[index]);
    if (point.x >= rect.x1 && point.x <= rect.x2 && point.y >= rect.y1 && point.y <= rect.y2) {
      return index;
    }
  }
  return -1;
}

function setCanvasMode(mode) {
  state.mode = mode;
  elements.drawModeButton.classList.toggle("active", mode === "draw");
  elements.panModeButton.classList.toggle("active", mode === "pan");
  elements.canvas.style.cursor = mode === "pan" ? "grab" : "crosshair";
}

function pointerDown(event) {
  if (!state.image) return;
  const point = canvasPoint(event);
  const usePan = event.button === 2 || event.button === 1 || state.mode === "pan";
  if (usePan) {
    state.interaction = {
      type: "pan",
      start: point,
      offsetX: state.view.offsetX,
      offsetY: state.view.offsetY,
    };
    elements.canvas.style.cursor = "grabbing";
    elements.canvas.setPointerCapture(event.pointerId);
    return;
  }
  if (event.button !== 0) return;

  const handle = hitHandle(point);
  if (handle) {
    state.interaction = {
      type: "resize",
      handle: handle.name,
      start: screenToImage(point.x, point.y, true),
      original: { ...state.boxes[state.selectedBox] },
      moved: false,
    };
    elements.canvas.setPointerCapture(event.pointerId);
    return;
  }

  const boxIndex = hitBox(point);
  if (boxIndex >= 0) {
    state.selectedBox = boxIndex;
    state.interaction = {
      type: "move",
      start: screenToImage(point.x, point.y, true),
      original: { ...state.boxes[boxIndex] },
      moved: false,
    };
    renderBoxList();
    drawCanvas();
    elements.canvas.setPointerCapture(event.pointerId);
    return;
  }

  const imagePoint = screenToImage(point.x, point.y, false);
  if (
    imagePoint.x < 0 || imagePoint.y < 0
    || imagePoint.x > state.image.naturalWidth || imagePoint.y > state.image.naturalHeight
  ) return;
  state.selectedBox = -1;
  state.interaction = { type: "draw", start: imagePoint, current: imagePoint };
  renderBoxList();
  elements.canvas.setPointerCapture(event.pointerId);
}

function pointerMove(event) {
  if (!state.interaction || !state.image) return;
  const point = canvasPoint(event);
  const action = state.interaction;
  if (action.type === "pan") {
    state.view.offsetX = action.offsetX + point.x - action.start.x;
    state.view.offsetY = action.offsetY + point.y - action.start.y;
  } else if (action.type === "draw") {
    action.current = screenToImage(point.x, point.y, true);
  } else if (action.type === "move") {
    const current = screenToImage(point.x, point.y, true);
    const dx = current.x - action.start.x;
    const dy = current.y - action.start.y;
    const width = action.original.x2 - action.original.x1;
    const height = action.original.y2 - action.original.y1;
    const x1 = Math.max(0, Math.min(state.image.naturalWidth - width, action.original.x1 + dx));
    const y1 = Math.max(0, Math.min(state.image.naturalHeight - height, action.original.y1 + dy));
    Object.assign(state.boxes[state.selectedBox], { x1, y1, x2: x1 + width, y2: y1 + height });
    action.moved ||= Math.abs(dx) > 0.2 || Math.abs(dy) > 0.2;
  } else if (action.type === "resize") {
    resizeSelectedBox(action, screenToImage(point.x, point.y, true));
  }
  if (action.type === "move" || action.type === "resize") scheduleTargetPreviews();
  drawCanvas();
}

function resizeSelectedBox(action, point) {
  const original = action.original;
  let { x1, y1, x2, y2 } = original;
  if (action.handle.includes("w")) x1 = point.x;
  if (action.handle.includes("e")) x2 = point.x;
  if (action.handle.includes("n")) y1 = point.y;
  if (action.handle.includes("s")) y2 = point.y;
  const minimum = Math.max(2, 6 / state.view.scale);
  if (x2 - x1 < minimum) {
    if (action.handle.includes("w")) x1 = x2 - minimum;
    else x2 = x1 + minimum;
  }
  if (y2 - y1 < minimum) {
    if (action.handle.includes("n")) y1 = y2 - minimum;
    else y2 = y1 + minimum;
  }
  x1 = Math.max(0, Math.min(state.image.naturalWidth, x1));
  x2 = Math.max(0, Math.min(state.image.naturalWidth, x2));
  y1 = Math.max(0, Math.min(state.image.naturalHeight, y1));
  y2 = Math.max(0, Math.min(state.image.naturalHeight, y2));
  Object.assign(state.boxes[state.selectedBox], { x1, y1, x2, y2 });
  action.moved = true;
}

function pointerUp(event) {
  if (!state.interaction) return;
  const action = state.interaction;
  if (action.type === "draw") {
    const x1 = Math.min(action.start.x, action.current.x);
    const y1 = Math.min(action.start.y, action.current.y);
    const x2 = Math.max(action.start.x, action.current.x);
    const y2 = Math.max(action.start.y, action.current.y);
    if ((x2 - x1) * state.view.scale >= 5 && (y2 - y1) * state.view.scale >= 5) {
      state.boxes.push({ cls_id: state.currentClass, x1, y1, x2, y2 });
      state.selectedBox = state.boxes.length - 1;
      setDirty(true);
    }
  } else if ((action.type === "move" || action.type === "resize") && action.moved) {
    setDirty(true);
  }
  state.interaction = null;
  elements.canvas.style.cursor = state.mode === "pan" ? "grab" : "crosshair";
  if (elements.canvas.hasPointerCapture(event.pointerId)) elements.canvas.releasePointerCapture(event.pointerId);
  renderBoxList();
  drawCanvas();
}

function zoomAt(point, factor) {
  if (!state.image) return;
  const anchor = screenToImage(point.x, point.y);
  const nextScale = Math.max(0.005, Math.min(32, state.view.scale * factor));
  state.view.scale = nextScale;
  state.view.offsetX = point.x - anchor.x * nextScale;
  state.view.offsetY = point.y - anchor.y * nextScale;
  drawCanvas();
}

function wheelCanvas(event) {
  if (!state.image) return;
  event.preventDefault();
  const point = canvasPoint(event);
  zoomAt(point, event.deltaY < 0 ? 1.12 : 1 / 1.12);
}

function zoomCenter(factor) {
  const size = canvasSize();
  zoomAt({ x: size.width / 2, y: size.height / 2 }, factor);
}

function checkedPredictionClasses() {
  return $$("#predictionClassFilters input:checked").map((input) => Number(input.value));
}

function predictionPayload() {
  return {
    model_path: elements.modelPath.value.trim(),
    confidence: Number(elements.confidenceRange.value),
    class_ids: checkedPredictionClasses(),
    device: elements.predictionDevice.value,
  };
}

async function predictCurrentImage() {
  if (!state.currentPath || !state.image) return;
  if ((state.dirty || state.boxes.length > 0) && !window.confirm("预标注结果将替换画布中的当前框，是否继续？")) return;
  elements.loadingOverlay.hidden = false;
  try {
    const payload = await api("/api/predict/one", {
      method: "POST",
      body: { ...predictionPayload(), image: state.currentPath },
    });
    state.boxes = payload.boxes.map((box) => normalizedToPixel(box, state.image));
    state.selectedBox = -1;
    elements.reviewedToggle.checked = false;
    setDirty(true);
    renderBoxList();
    drawCanvas();
    localStorage.setItem("cc_training_materials.model", elements.modelPath.value.trim());
    showToast(`预标注得到 ${state.boxes.length} 个框`);
  } catch (error) {
    showToast(error.message, "error", 6000);
  } finally {
    elements.loadingOverlay.hidden = true;
  }
}

async function startBulkPrediction() {
  if (state.dirty && !window.confirm("当前图片有未保存修改，开始任务将放弃这些修改，是否继续？")) return;
  const overwrite = elements.overwritePolicy.value;
  if (overwrite === "replace_all" && !window.confirm("该操作会覆盖范围内的人工标签，原标签会备份。确定继续吗？")) return;
  try {
    const payload = {
      ...predictionPayload(),
      scope: elements.predictionScope.value,
      overwrite,
    };
    const job = await api("/api/jobs/predict", { method: "POST", body: payload });
    localStorage.setItem("cc_training_materials.model", elements.modelPath.value.trim());
    state.job = job;
    setDirty(false);
    renderJob(job);
    startJobPolling();
    updateControlState();
  } catch (error) {
    showToast(error.message, "error", 6000);
  }
}

function normalizeWeatherReview(payload) {
  return {
    ...payload,
    approved: new Set(payload.items.filter((item) => item.approved).map((item) => item.id)),
    signature: weatherSettingsSignature(payload),
  };
}

async function loadWeatherReview(reviewId = "", openDialog = false) {
  const params = new URLSearchParams();
  if (reviewId) params.set("id", reviewId);
  const payload = await api(`/api/weather/review?${params}`);
  state.weatherReview = normalizeWeatherReview(payload);
  if (payload.materialized_now) {
    const config = await api("/api/config");
    applyDataset(config.dataset);
    await loadImages(true);
    await loadTrainingPlan();
  }
  updateWeatherReviewStatus();
  updateControlState();
  if (openDialog) openWeatherReviewDialog();
  return state.weatherReview;
}

function weatherReviewImageUrl(item) {
  const params = new URLSearchParams({
    review_id: state.weatherReview.id,
    item_id: item.id,
  });
  return `/api/weather/image?${params}`;
}

function loadImageUrl(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("审核图片加载失败"));
    image.src = url;
  });
}

function drawWeatherReviewCanvas(canvas, image, boxes, predictions) {
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.fillStyle = "#202529";
  context.fillRect(0, 0, width, height);
  const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight);
  const drawWidth = image.naturalWidth * scale;
  const drawHeight = image.naturalHeight * scale;
  const offsetX = (width - drawWidth) / 2;
  const offsetY = (height - drawHeight) / 2;
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(image, offsetX, offsetY, drawWidth, drawHeight);
  const drawNormalizedBox = (box, color, dashed, label) => {
    const x = offsetX + (Number(box.xc) - Number(box.w) / 2) * drawWidth;
    const y = offsetY + (Number(box.yc) - Number(box.h) / 2) * drawHeight;
    const boxWidth = Number(box.w) * drawWidth;
    const boxHeight = Number(box.h) * drawHeight;
    context.strokeStyle = color;
    context.lineWidth = dashed ? 3 : 4;
    context.setLineDash(dashed ? [10, 7] : []);
    context.strokeRect(x, y, boxWidth, boxHeight);
    context.setLineDash([]);
    context.font = "bold 16px sans-serif";
    const textWidth = context.measureText(label).width + 10;
    const labelY = Math.max(0, y - 22);
    context.fillStyle = color;
    context.fillRect(x, labelY, textWidth, 22);
    context.fillStyle = "#fff";
    context.fillText(label, x + 5, labelY + 16);
  };
  for (const box of boxes || []) {
    drawNormalizedBox(box, colorForClass(Number(box.cls_id)), false, `人工 ${className(Number(box.cls_id))}`);
  }
  for (const prediction of predictions || []) {
    const confidence = Number(prediction.confidence || 0).toFixed(2);
    drawNormalizedBox(
      prediction,
      "#f1b83b",
      true,
      `模型 ${className(Number(prediction.cls_id))} ${confidence}`,
    );
  }
}

async function focusWeatherReviewItem(itemId) {
  const review = state.weatherReview;
  const item = review?.items.find((value) => value.id === itemId);
  if (!item) return;
  state.weatherFocusId = itemId;
  elements.weatherReviewGallery.querySelectorAll(".weather-review-item").forEach((card) => {
    card.classList.toggle("focused", card.dataset.itemId === itemId);
  });
  elements.weatherEnhancedTitle.textContent = `增强图 · ${WEATHER_LABELS[item.weather] || item.weather}`;
  elements.weatherFocusedName.textContent = item.source_name;
  elements.weatherFocusedName.title = item.source_name;
  const analysis = item.analysis || {};
  const reasons = analysis.reasons?.length ? analysis.reasons.join(" · ") : "模型表现稳定";
  elements.weatherGapSummary.textContent = `${reasons} · 原图命中 ${analysis.original_hits || 0}/${analysis.ground_truth || 0} · 天气图命中 ${analysis.weather_hits || 0}/${analysis.ground_truth || 0} · 困难分 ${Number(analysis.score || 0).toFixed(1)}`;
  const token = ++state.weatherLoadToken;
  try {
    const [original, enhanced] = await Promise.all([
      loadImageUrl(`/api/image?path=${encodeURIComponent(item.source_name)}`),
      loadImageUrl(weatherReviewImageUrl(item)),
    ]);
    if (token !== state.weatherLoadToken) return;
    drawWeatherReviewCanvas(elements.weatherOriginalCanvas, original, item.boxes, item.original_predictions);
    drawWeatherReviewCanvas(elements.weatherEnhancedCanvas, enhanced, item.boxes, item.weather_predictions);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function updateWeatherReviewSelection() {
  const review = state.weatherReview;
  if (!review) return;
  elements.weatherReviewSelection.textContent = `已选择 ${review.approved.size} / ${review.items.length}`;
  const hardCount = Number(review.summary?.hard || 0);
  const originalRecall = review.summary?.original_recall == null
    ? "--"
    : `${(Number(review.summary.original_recall) * 100).toFixed(1)}%`;
  const weatherRecall = review.summary?.weather_recall == null
    ? "--"
    : `${(Number(review.summary.weather_recall) * 100).toFixed(1)}%`;
  elements.weatherReviewSummary.textContent = `困难 ${hardCount}/${review.items.length} · 原图召回 ${originalRecall} · 天气召回 ${weatherRecall}`;
  elements.weatherReviewGallery.querySelectorAll(".weather-review-item").forEach((card) => {
    const approved = review.approved.has(card.dataset.itemId);
    card.classList.toggle("excluded", !approved);
    const checkbox = card.querySelector("input[type=checkbox]");
    if (checkbox) checkbox.checked = approved;
  });
}

function renderWeatherReviewGallery() {
  const review = state.weatherReview;
  elements.weatherReviewGallery.replaceChildren();
  const visibleItems = review?.items.filter(
    (item) => state.weatherReviewFilter === "all" || Boolean(item.analysis?.hard),
  ) || [];
  if (!visibleItems.length) {
    const empty = document.createElement("div");
    empty.className = "list-empty";
    empty.textContent = state.weatherReviewFilter === "hard" ? "没有需要复核的困难素材" : "没有天气审核素材";
    elements.weatherReviewGallery.append(empty);
    updateWeatherReviewSelection();
    return;
  }
  for (const item of visibleItems) {
    const card = document.createElement("div");
    card.className = `weather-review-item ${item.analysis?.hard ? "hard" : ""}`;
    card.dataset.itemId = item.id;
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = review.approved.has(item.id);
    checkbox.setAttribute("aria-label", `保留 ${item.original_name}`);
    checkbox.addEventListener("click", (event) => event.stopPropagation());
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) review.approved.add(item.id);
      else review.approved.delete(item.id);
      review.confirmed = false;
      updateWeatherReviewSelection();
      updateWeatherReviewStatus();
      updateControlState();
    });
    const image = document.createElement("img");
    image.loading = "lazy";
    image.alt = `${WEATHER_LABELS[item.weather] || item.weather} ${item.original_name}`;
    image.src = weatherReviewImageUrl(item);
    const meta = document.createElement("div");
    meta.className = "weather-review-item-meta";
    const name = document.createElement("strong");
    name.textContent = item.original_name;
    const weather = document.createElement("span");
    weather.textContent = WEATHER_LABELS[item.weather] || item.weather;
    const reason = document.createElement("span");
    reason.className = "weather-review-reason";
    reason.textContent = item.analysis?.reasons?.join(" · ") || "表现稳定";
    meta.append(name, weather, reason);
    card.append(checkbox, image, meta);
    card.addEventListener("click", () => focusWeatherReviewItem(item.id));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        focusWeatherReviewItem(item.id);
      }
    });
    elements.weatherReviewGallery.append(card);
  }
  updateWeatherReviewSelection();
  const focusId = visibleItems.some((item) => item.id === state.weatherFocusId)
    ? state.weatherFocusId
    : visibleItems[0].id;
  focusWeatherReviewItem(focusId);
}

function openWeatherReviewDialog() {
  if (!state.weatherReview) return;
  state.weatherReviewFilter = state.weatherReview.analysis_version === 1 ? "hard" : "all";
  elements.showHardWeatherButton.classList.toggle("active", state.weatherReviewFilter === "hard");
  elements.showAllWeatherButton.classList.toggle("active", state.weatherReviewFilter === "all");
  renderWeatherReviewGallery();
  elements.weatherReviewDialog.showModal();
}

function setWeatherReviewFilter(filter) {
  state.weatherReviewFilter = filter;
  elements.showHardWeatherButton.classList.toggle("active", filter === "hard");
  elements.showAllWeatherButton.classList.toggle("active", filter === "all");
  renderWeatherReviewGallery();
}

function setAllWeatherReviewItems(approved) {
  const review = state.weatherReview;
  if (!review) return;
  review.approved = approved ? new Set(review.items.map((item) => item.id)) : new Set();
  review.confirmed = false;
  updateWeatherReviewSelection();
  updateWeatherReviewStatus();
  updateControlState();
}

async function confirmWeatherReview() {
  const review = state.weatherReview;
  if (!review) return;
  try {
    const payload = await api("/api/weather/review/save", {
      method: "POST",
      body: { review_id: review.id, approved_ids: Array.from(review.approved) },
    });
    state.weatherReview = normalizeWeatherReview(payload);
    elements.weatherReviewDialog.close();
    const config = await api("/api/config");
    applyDataset(config.dataset);
    await loadImages(true);
    await loadTrainingPlan();
    updateControlState();
    const added = Number(payload.materialized?.added || 0);
    const removed = Number(payload.materialized?.removed || 0);
    showToast(`已加入数据集 ${state.weatherReview.materialized_count} 张（新增 ${added}，移除 ${removed}）`, "normal", 6200);
  } catch (error) {
    showToast(error.message, "error", 6200);
  }
}

async function startWeatherReview() {
  if (state.dirty) {
    showToast("请先保存当前图片标签，再生成天气素材", "warning", 5200);
    return;
  }
  try {
    const settings = currentWeatherSettings();
    const job = await api("/api/weather/review/start", { method: "POST", body: settings });
    state.job = job;
    renderJob(job);
    startJobPolling();
    updateControlState();
  } catch (error) {
    showToast(error.message, "error", 6200);
  }
}

async function startTraining() {
  if (state.dirty && !window.confirm("当前图片有未保存修改，开始训练将放弃这些修改，是否继续？")) return;
  try {
    const payload = {
      model_path: elements.trainingModelPath.value.trim(),
      epochs: Number(elements.trainingEpochs.value),
      batch: Number(elements.trainingBatch.value),
      image_size: Number(elements.trainingImageSize.value),
      validation_ratio: Number(elements.validationRatio.value) / 100,
      weather_types: $$("#weatherOptions input:checked").map((input) => input.value),
      weather_ratio: Number(elements.weatherRatio.value) / 100,
      weather_review_id: state.weatherReview?.id || "",
      training_scope: elements.trainingScope.value,
      device: elements.trainingDevice.value,
    };
    const job = await api("/api/jobs/train", { method: "POST", body: payload });
    localStorage.setItem("cc_training_materials.training_model", elements.trainingModelPath.value.trim());
    state.job = job;
    setDirty(false);
    elements.trainingSummary.hidden = true;
    renderJob(job);
    startJobPolling();
    updateControlState();
  } catch (error) {
    showToast(error.message, "error", 7000);
  }
}

let trainingPlanTimer = null;

async function loadTrainingPlan() {
  const modelPath = elements.trainingModelPath.value.trim();
  if (!state.dataset?.open || !modelPath.endsWith(".pt")) {
    state.trainingPlan = null;
    elements.trainingDataPlan.textContent = "请选择训练权重";
    elements.trainingDataPlan.classList.add("warning");
    updateControlState();
    return;
  }
  elements.trainingDataPlan.textContent = "正在统计训练图片";
  elements.trainingDataPlan.classList.remove("warning");
  try {
    const params = new URLSearchParams({
      model_path: modelPath,
      training_scope: elements.trainingScope.value,
    });
    const plan = await api(`/api/training/plan?${params}`);
    if (elements.trainingModelPath.value.trim() !== modelPath) return;
    state.trainingPlan = plan;
    const scopeText = plan.scope === "all_reviewed"
      ? `全部已复核 ${plan.selected_images} 张`
      : `新增 ${plan.incremental_images} 张 · 回放 ${plan.replay_images} 张 · 本次 ${plan.selected_images} 张`;
    elements.trainingDataPlan.textContent = `${scopeText} · 模型时间 ${plan.cutoff.replace("T", " ")}`;
    elements.trainingDataPlan.classList.toggle("warning", plan.selected_images < 2);
  } catch (error) {
    state.trainingPlan = null;
    elements.trainingDataPlan.textContent = error.message;
    elements.trainingDataPlan.classList.add("warning");
  }
  updateControlState();
}

function scheduleTrainingPlan() {
  window.clearTimeout(trainingPlanTimer);
  trainingPlanTimer = window.setTimeout(loadTrainingPlan, 280);
}

function renderJob(job) {
  state.job = job;
  if (!job || job.status === "idle") {
    elements.jobBar.hidden = true;
    updateControlState();
    return;
  }
  elements.jobBar.hidden = false;
  const jobKindLabels = {
    training: "模型训练",
    prediction: "自动标注",
    weather_review: "天气素材检测",
    export: "导出 9:1",
  };
  elements.jobKind.textContent = jobKindLabels[job.kind] || "后台任务";
  elements.jobMessage.textContent = job.message || "处理中";
  elements.jobMessage.title = job.current_image || job.message || "";
  const progress = Math.max(0, Math.min(100, Number(job.progress) || 0));
  elements.jobCounter.textContent = `${Number.isInteger(progress) ? progress : progress.toFixed(1)}%`;
  elements.jobProgressFill.style.width = `${progress}%`;

  const details = [];
  const phaseNames = {
    preparing: "准备数据",
    weather: "天气增强",
    weather_review: "生成并检测素材",
    initializing: "初始化",
    training: "训练",
    validating: "验证",
    saving: "保存权重",
    finishing: "整理结果",
    exporting: "复制图片和标签",
    cancelling: "停止中",
  };
  if (job.phase && phaseNames[job.phase]) details.push(`阶段 ${phaseNames[job.phase]}`);
  if (job.kind === "training") {
    if (job.epochs) details.push(`轮次 ${job.epoch || 0}/${job.epochs}`);
    if (job.batches) details.push(`批次 ${job.batch || 0}/${job.batches}`);
  } else if (job.total) {
    details.push(`图片 ${job.current || 0}/${job.total}`);
  }
  const elapsed = formatDuration(Number(job.elapsed_seconds));
  const eta = job.eta_seconds == null ? "" : formatDuration(Number(job.eta_seconds));
  if (elapsed) details.push(`已用 ${elapsed}`);
  if (eta && !job.cancel_requested) details.push(`预计剩余 ${eta}`);
  const metricLabels = {
    box_loss: "框损失",
    cls_loss: "分类损失",
    dfl_loss: "定位损失",
    precision: "精确率",
    recall: "召回率",
    map50: "mAP50",
    map50_95: "mAP50-95",
  };
  for (const [key, label] of Object.entries(metricLabels)) {
    const value = Number(job.metrics?.[key]);
    if (Number.isFinite(value)) details.push(`${label} ${value.toFixed(4)}`);
  }
  elements.jobDetails.textContent = details.join(" · ");
  elements.jobDetails.hidden = details.length === 0;
  elements.cancelJobButton.hidden = job.status !== "running";
  elements.cancelJobButton.disabled = Boolean(job.cancel_requested);
  elements.cancelJobButton.textContent = job.cancel_requested ? "停止中" : "停止";
  updateControlState();
}

function startJobPolling() {
  if (state.jobTimer) return;
  state.jobTimer = window.setInterval(pollJob, 900);
}

async function pollJob() {
  try {
    const job = await api("/api/job");
    renderJob(job);
    if (job.status !== "running" && job.status !== "idle") {
      window.clearInterval(state.jobTimer);
      state.jobTimer = null;
      await handleFinishedJob(job);
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function handleFinishedJob(job) {
  const key = `${job.id}:${job.status}`;
  if (state.handledJobKey === key) return;
  state.handledJobKey = key;
  if (job.status === "completed") {
    if (job.kind === "prediction") {
      const result = job.result || {};
      state.weatherReview = null;
      showToast(`自动标注完成：${result.processed || 0} 张图片，${result.boxes || 0} 个框`, "normal", 6000);
      await loadImages(true);
      if (state.currentPath) await loadImage(state.currentPath, true);
    } else if (job.kind === "video_extract") {
      const result = job.result || {};
      showToast(
        `视频抽帧完成：${result.frames || 0} 张 PNG。接下来请选择扫描去重或直接添加。`,
        "normal",
        7000,
      );
      if (result.output_dir) prepareImageSource(result.output_dir);
    } else if (job.kind === "weather_review") {
      const result = job.result || {};
      await loadWeatherReview(result.review_id, true);
      showToast(`天气检测完成：${result.generated || 0} 张，困难素材 ${result.hard || 0} 张`, "normal", 6200);
    } else if (job.kind === "training") {
      const result = job.result || {};
      const bestModel = result.best_model || "未生成 best.pt";
      const weatherImages = result.weather_images || 0;
      const skippedPending = result.skipped_pending || 0;
      const incrementalImages = result.incremental_images || 0;
      const replayImages = result.replay_images || 0;
      elements.trainingSummary.textContent = `训练完成。新增已复核 ${incrementalImages} 张，历史回放 ${replayImages} 张，天气素材 ${weatherImages} 张，排除待复核 ${skippedPending} 张。best.pt: ${bestModel}`;
      elements.trainingSummary.hidden = false;
      if (result.best_model) {
        elements.modelPath.value = result.best_model;
        elements.trainingModelPath.value = result.best_model;
        localStorage.setItem("cc_training_materials.model", result.best_model);
        localStorage.setItem("cc_training_materials.training_model", result.best_model);
        loadTrainingPlan();
      }
      showToast("模型训练完成", "normal", 6000);
    } else if (job.kind === "export") {
      const result = job.result || {};
      showToast(`导出完成：训练 ${result.train || 0} 张，验证 ${result.val || 0} 张。${result.output || ""}`, "normal", 9000);
    }
  } else if (job.status === "failed") {
    showToast(job.error || "后台任务失败", "error", 9000);
  } else if (job.status === "cancelled") {
    showToast("后台任务已取消", "warning");
    if (job.kind === "prediction") await loadImages(true);
  }
  window.setTimeout(() => {
    if (state.job?.status !== "running") elements.jobBar.hidden = true;
  }, 8000);
  updateControlState();
}

async function cancelJob() {
  if (!window.confirm("确定停止当前任务吗？")) return;
  try {
    const job = await api("/api/jobs/cancel", { method: "POST", body: {} });
    renderJob(job);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function startDatasetExport(parentDirectory) {
  const parent = String(parentDirectory || "").replace(/\/+$/, "") || "/";
  const outputPath = parent === "/" ? "/yolo_dataset_9_1" : `${parent}/yolo_dataset_9_1`;
  if (!window.confirm(`将当前全部带标签图片统一打乱并按 9:1 导出到：\n${outputPath}\n\n图片和标签直接放入 train/val，不保留来源子目录。已有导出将被替换，源数据不会移动或删除。`)) return;
  try {
    const job = await api("/api/jobs/export", {
      method: "POST",
      body: { output_path: outputPath, overwrite: true },
    });
    state.job = job;
    renderJob(job);
    startJobPolling();
    updateControlState();
  } catch (error) {
    showToast(error.message, "error", 7000);
  }
}

async function openBrowser(kind, purpose, choose, startPath = null) {
  state.browser = {
    kind,
    purpose,
    choose,
    current: startPath || state.dataset?.root || "/hdd",
    selected: null,
  };
  elements.browserTitle.textContent = kind === "model"
    ? "选择 YOLO 权重"
    : kind === "video"
      ? "选择视频文件"
    : purpose === "source"
      ? "选择图片目录"
      : purpose === "export"
        ? "选择导出位置"
        : "选择数据集根目录";
  elements.browserPurpose.textContent = purpose === "export"
    ? "统一随机划分，文件直接放入 train/val"
    : kind === "model"
      ? "支持 .pt 文件"
      : kind === "video"
        ? "支持 MP4、AVI、MOV、MKV、WEBM 等视频"
      : "本机文件系统";
  elements.chooseCurrentButton.textContent = kind === "model"
    ? "选择模型"
    : kind === "video"
      ? "选择视频"
      : purpose === "export"
        ? "导出到这里"
        : "选择当前目录";
  elements.chooseCurrentButton.disabled = kind === "model" || kind === "video";
  elements.browserDialog.showModal();
  await loadBrowserDirectory(state.browser.current);
}

async function loadBrowserDirectory(path) {
  try {
    const params = new URLSearchParams({ kind: state.browser.kind, path });
    const payload = await api(`/api/filesystem?${params}`);
    state.browser.current = payload.current;
    state.browser.selected = null;
    elements.browserPathInput.value = payload.current;
    elements.browserParentButton.disabled = !payload.parent;
    elements.browserParentButton.dataset.path = payload.parent || "";
    elements.browserSelection.textContent = payload.current;
    elements.chooseCurrentButton.disabled = state.browser.kind === "model" || state.browser.kind === "video";
    renderBrowserEntries(payload.entries);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderBrowserEntries(entries) {
  elements.browserEntries.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "list-empty";
    empty.textContent = "该目录没有可显示的内容";
    elements.browserEntries.append(empty);
    return;
  }
  for (const entry of entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `browser-entry ${entry.type === "file" ? "file" : ""}`;
    const marker = document.createElement("span");
    marker.className = "entry-type";
    marker.textContent = entry.type === "directory" ? ">" : (entry.file_type || "FILE");
    const name = document.createElement("strong");
    name.textContent = entry.name;
    const detail = document.createElement("small");
    detail.textContent = entry.type === "file" ? formatBytes(entry.size) : "目录";
    button.append(marker, name, detail);
    button.addEventListener("click", () => {
      if (entry.type === "directory") {
        loadBrowserDirectory(entry.path);
      } else {
        $$(".browser-entry.selected").forEach((item) => item.classList.remove("selected"));
        button.classList.add("selected");
        state.browser.selected = entry.path;
        elements.browserSelection.textContent = entry.path;
        elements.chooseCurrentButton.disabled = false;
      }
    });
    elements.browserEntries.append(button);
  }
}

function chooseBrowserValue() {
  const value = state.browser.kind === "model" || state.browser.kind === "video"
    ? state.browser.selected
    : state.browser.current;
  if (!value) return;
  const choose = state.browser.choose;
  elements.browserDialog.close();
  choose?.(value);
}

function switchToolTab(tabName) {
  $$("#rightTabs button").forEach((button) => button.classList.toggle("active", button.dataset.tab === tabName));
  $$(".tool-tab").forEach((tab) => tab.classList.toggle("active", tab.id === `${tabName}Tab`));
}

function bindEvents() {
  elements.openDatasetButton.addEventListener("click", () => openBrowser("directory", "dataset", openDataset));
  elements.emptyOpenButton.addEventListener("click", () => openBrowser("directory", "dataset", openDataset));
  elements.newProjectButton.addEventListener("click", () => elements.newProjectDialog.showModal());
  elements.exportDatasetButton.addEventListener("click", () => {
    const root = state.dataset?.root || "/data/cc_training_materials/dataset";
    const parent = root.includes("/") ? root.slice(0, root.lastIndexOf("/")) || "/" : "/";
    openBrowser("directory", "export", startDatasetExport, parent);
  });
  elements.closeNewProjectButton.addEventListener("click", () => elements.newProjectDialog.close());
  elements.cancelNewProjectButton.addEventListener("click", () => elements.newProjectDialog.close());
  elements.newProjectForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const path = elements.newProjectPath.value.trim();
    elements.newProjectDialog.close();
    openDataset(path, { create: true });
  });
  elements.addSourceButton.addEventListener("click", () => {
    openBrowser("directory", "source", prepareImageSource, sourceBrowserStartPath());
  });
  elements.addVideoButton.addEventListener("click", () => {
    openBrowser("video", "video", prepareVideo, sourceBrowserStartPath());
  });
  elements.dedupForm.addEventListener("submit", scanImageSource);
  elements.directAddButton.addEventListener("click", addImageSourceDirect);
  elements.stopDedupButton.addEventListener("click", stopImageSourceScan);
  elements.dedupThreshold.addEventListener("input", invalidateDedupScan);
  elements.applyDedupButton.addEventListener("click", applyImageSourceDedup);
  elements.closeDedupButton.addEventListener("click", () => elements.dedupDialog.close());
  elements.cancelDedupButton.addEventListener("click", () => elements.dedupDialog.close());
  elements.dedupDialog.addEventListener("cancel", (event) => {
    if (state.dedup.busy) event.preventDefault();
  });
  elements.videoForm.addEventListener("submit", startVideoExtraction);
  elements.closeVideoButton.addEventListener("click", () => elements.videoDialog.close());
  elements.cancelVideoButton.addEventListener("click", () => elements.videoDialog.close());
  elements.videoDialog.addEventListener("cancel", (event) => {
    if (state.job?.status === "running" && state.job?.kind === "video_extract") event.preventDefault();
  });

  elements.imageFilters.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-filter]");
    if (!button || button.dataset.filter === state.filter) return;
    if (!canDiscardChanges()) return;
    resetCurrentImage();
    setImageFilter(button.dataset.filter);
    await loadImages(true);
    await openFirstListedImage();
  });
  let searchTimer = null;
  elements.imageSearch.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.search = elements.imageSearch.value.trim();
      loadImages(true);
    }, 240);
  });
  elements.imageSort.addEventListener("change", () => {
    state.sort = elements.imageSort.value;
    loadImages(true);
  });
  elements.loadMoreButton.addEventListener("click", () => loadImages(false));
  elements.imageList.addEventListener("scroll", () => {
    state.imageListScrollTop = elements.imageList.scrollTop;
  }, { passive: true });
  elements.previousButton.addEventListener("click", () => navigateImage(-1));
  elements.nextButton.addEventListener("click", () => navigateImage(1));
  elements.drawModeButton.addEventListener("click", () => setCanvasMode("draw"));
  elements.panModeButton.addEventListener("click", () => setCanvasMode("pan"));
  elements.zoomOutButton.addEventListener("click", () => zoomCenter(1 / 1.15));
  elements.zoomInButton.addEventListener("click", () => zoomCenter(1.15));
  elements.fitButton.addEventListener("click", fitImage);
  elements.deleteImageButton.addEventListener("click", deleteCurrentImage);
  elements.saveButton.addEventListener("click", saveLabels);
  elements.reviewedToggle.addEventListener("change", () => {
    state.reviewed = elements.reviewedToggle.checked;
    setDirty(true);
  });
  elements.addClassButton.addEventListener("click", addClassEditorRow);
  elements.saveClassesButton.addEventListener("click", saveClasses);
  elements.clearBoxesButton.addEventListener("click", clearBoxes);

  elements.rightTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (button) switchToolTab(button.dataset.tab);
  });
  elements.confidenceRange.addEventListener("input", () => {
    elements.confidenceOutput.value = Number(elements.confidenceRange.value).toFixed(2);
  });
  elements.modelPath.addEventListener("input", updateControlState);
  elements.trainingModelPath.addEventListener("input", () => {
    state.trainingPlan = null;
    invalidateWeatherReview();
    scheduleTrainingPlan();
  });
  elements.trainingScope.addEventListener("change", () => {
    invalidateWeatherReview();
    loadTrainingPlan();
  });
  elements.validationRatio.addEventListener("input", invalidateWeatherReview);
  elements.weatherOptions.addEventListener("change", invalidateWeatherReview);
  elements.weatherRatio.addEventListener("input", () => {
    elements.weatherRatioOutput.value = `${elements.weatherRatio.value}%`;
    invalidateWeatherReview();
  });
  elements.browseModelButton.addEventListener("click", () => openBrowser("model", "model", (path) => {
    elements.modelPath.value = path;
    updateControlState();
  }, elements.modelPath.value || state.dataset?.root));
  elements.browseTrainingModelButton.addEventListener("click", () => openBrowser("model", "training-model", (path) => {
    elements.trainingModelPath.value = path;
    invalidateWeatherReview();
    loadTrainingPlan();
  }, elements.trainingModelPath.value || state.dataset?.root));
  elements.predictCurrentButton.addEventListener("click", predictCurrentImage);
  elements.startPredictionButton.addEventListener("click", startBulkPrediction);
  elements.generateWeatherReviewButton.addEventListener("click", startWeatherReview);
  elements.openWeatherReviewButton.addEventListener("click", openWeatherReviewDialog);
  elements.approveAllWeatherButton.addEventListener("click", () => setAllWeatherReviewItems(true));
  elements.rejectAllWeatherButton.addEventListener("click", () => setAllWeatherReviewItems(false));
  elements.showHardWeatherButton.addEventListener("click", () => setWeatherReviewFilter("hard"));
  elements.showAllWeatherButton.addEventListener("click", () => setWeatherReviewFilter("all"));
  elements.closeWeatherReviewButton.addEventListener("click", () => elements.weatherReviewDialog.close());
  elements.cancelWeatherReviewButton.addEventListener("click", () => elements.weatherReviewDialog.close());
  elements.confirmWeatherReviewButton.addEventListener("click", confirmWeatherReview);
  elements.startTrainingButton.addEventListener("click", startTraining);
  elements.predictionScope.addEventListener("change", () => {
    if (elements.predictionScope.value === "pending" && elements.overwritePolicy.value === "skip_existing") {
      elements.overwritePolicy.value = "replace_predictions";
    }
  });
  elements.cancelJobButton.addEventListener("click", cancelJob);

  elements.browserParentButton.addEventListener("click", () => loadBrowserDirectory(elements.browserParentButton.dataset.path));
  elements.browserGoButton.addEventListener("click", () => loadBrowserDirectory(elements.browserPathInput.value));
  elements.browserPathInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      loadBrowserDirectory(elements.browserPathInput.value);
    }
  });
  elements.chooseCurrentButton.addEventListener("click", chooseBrowserValue);

  elements.canvas.addEventListener("pointerdown", pointerDown);
  elements.canvas.addEventListener("pointermove", pointerMove);
  elements.canvas.addEventListener("pointerup", pointerUp);
  elements.canvas.addEventListener("pointercancel", pointerUp);
  elements.canvas.addEventListener("wheel", wheelCanvas, { passive: false });
  elements.canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  elements.canvas.tabIndex = 0;

  window.addEventListener("keydown", async (event) => {
    const tag = document.activeElement?.tagName;
    if (document.querySelector("dialog[open]")) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(tag) || document.activeElement?.isContentEditable) return;
    if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;

    if (event.key === "Delete" && state.selectedBox >= 0) {
      event.preventDefault();
      removeBox(state.selectedBox);
      return;
    }
    if (/^[1-9]$/.test(event.key)) {
      const classId = Number(event.key) - 1;
      if (state.classes.some((item) => item.id === classId)) {
        event.preventDefault();
        state.currentClass = classId;
        renderClassControls();
      }
      return;
    }
    if (event.key.toLowerCase() === "d" && state.currentPath) {
      event.preventDefault();
      await deleteCurrentImage();
      return;
    }
    if (event.key.toLowerCase() === "w" && state.currentPath) {
      event.preventDefault();
      await navigateImage(-1);
      return;
    }
    if (event.key.toLowerCase() === "s" && state.currentPath) {
      event.preventDefault();
      await navigateImage(1);
      return;
    }
    if ((event.key === "Enter" || event.code === "Space") && state.currentPath) {
      event.preventDefault();
      await saveLabels();
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
  new ResizeObserver(resizeCanvas).observe(elements.canvasStage);
}

async function initialize() {
  bindEvents();
  renderClassEditor();
  renderClassControls();
  renderBoxList();
  setCanvasMode("draw");
  resizeCanvas();

  const savedModel = localStorage.getItem("cc_training_materials.model") || "";
  const savedTrainingModel = localStorage.getItem("cc_training_materials.training_model") || "";
  elements.modelPath.value = savedModel;
  elements.trainingModelPath.value = savedTrainingModel;

  try {
    const config = await api("/api/config");
    elements.dependencyBadge.textContent = config.ultralytics
      ? `Ultralytics ${config.ultralytics}`
      : "训练依赖未安装";
    elements.dependencyBadge.className = `status-badge ${config.ultralytics ? "ok" : "warning"}`;
    state.job = config.job;
    if (!elements.modelPath.value && config.default_model) elements.modelPath.value = config.default_model;
    if (config.latest_trained_model) {
      elements.trainingModelPath.value = config.latest_trained_model;
      localStorage.setItem("cc_training_materials.training_model", config.latest_trained_model);
    } else if (!elements.trainingModelPath.value && config.default_model) {
      elements.trainingModelPath.value = config.default_model;
    }

    if (config.dataset?.open) {
      applyDataset(config.dataset);
      await openDefaultPendingImage();
      await loadTrainingPlan();
    } else {
      const savedDataset = localStorage.getItem("cc_training_materials.dataset");
      if (savedDataset) await openDataset(savedDataset);
    }
    if (state.dataset?.open) {
      try {
        await loadWeatherReview("", false);
      } catch (error) {
        if (error.status !== 404) showToast(error.message, "error", 5200);
      }
    }
    if (config.job?.status === "running") {
      renderJob(config.job);
      startJobPolling();
    }
  } catch (error) {
    elements.dependencyBadge.textContent = "服务连接失败";
    elements.dependencyBadge.className = "status-badge warning";
    showToast(error.message, "error", 7000);
  }
  updateControlState();
}

initialize();
