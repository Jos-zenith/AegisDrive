#include <Arduino.h>
#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// Wi-Fi settings
const char* ssid = "Redmi";
const char* password = "YOUR_WIFI_PASSWORD";

// AI-Thinker ESP32-CAM pin mapping
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5

#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

httpd_handle_t camera_server = NULL;

static const char* STREAM_TYPE =
    "multipart/x-mixed-replace;boundary=frame";

static const char* STREAM_BOUNDARY =
    "\r\n--frame\r\n";

static const char* STREAM_PART =
    "Content-Type: image/jpeg\r\n"
    "Content-Length: %u\r\n\r\n";

// Browser home page
static esp_err_t index_handler(httpd_req_t* req) {
  const char page[] =
      "<!DOCTYPE html><html><head>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<title>ESP32-CAM</title></head>"
      "<body style='text-align:center;font-family:Arial'>"
      "<h2>AI Accident Prevention System</h2>"
      "<p>Live Road Camera</p>"
      "<img src='/stream' style='width:100%;max-width:640px'>"
      "</body></html>";

  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, page, HTTPD_RESP_USE_STRLEN);
}

// Live MJPEG video stream
static esp_err_t stream_handler(httpd_req_t* req) {
  esp_err_t res = httpd_resp_set_type(req, STREAM_TYPE);

  if (res != ESP_OK) {
    return res;
  }

  httpd_resp_set_hdr(
      req, "Access-Control-Allow-Origin", "*"
  );

  char part_buffer[64];

  while (true) {
    camera_fb_t* fb = esp_camera_fb_get();

    if (fb == NULL) {
      Serial.println("Camera frame capture failed");
      return ESP_FAIL;
    }

    res = httpd_resp_send_chunk(
        req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY)
    );

    if (res == ESP_OK) {
      int header_length = snprintf(
          part_buffer,
          sizeof(part_buffer),
          STREAM_PART,
          (unsigned int)fb->len
      );

      res = httpd_resp_send_chunk(
          req, part_buffer, header_length
      );
    }

    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(
          req,
          (const char*)fb->buf,
          fb->len
      );
    }

    esp_camera_fb_return(fb);

    if (res != ESP_OK) {
      break;
    }
  }

  return res;
}

// Start the web server
void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();

  config.server_port = 80;
  config.ctrl_port = 32768;

  httpd_uri_t index_uri = {};
  index_uri.uri = "/";
  index_uri.method = HTTP_GET;
  index_uri.handler = index_handler;

  httpd_uri_t stream_uri = {};
  stream_uri.uri = "/stream";
  stream_uri.method = HTTP_GET;
  stream_uri.handler = stream_handler;

  if (httpd_start(&camera_server, &config) == ESP_OK) {
    httpd_register_uri_handler(
        camera_server, &index_uri
    );

    httpd_register_uri_handler(
        camera_server, &stream_uri
    );

    Serial.println("Camera web server started");
  } else {
    Serial.println("Failed to start camera web server");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("AI Accident Prevention - ESP32-CAM");

  // Camera configuration
  camera_config_t config = {};

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;

  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  if (psramFound()) {
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
    config.fb_count = 2;
  } else {
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  // Initialize camera
  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf(
        "Camera initialization failed: 0x%x\n", err
    );
    return;
  }

  Serial.println("Camera initialized successfully");

  // Connect to Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(ssid, password);

  Serial.print("Connecting to Wi-Fi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Wi-Fi connected");

  // Start camera streaming server
  startCameraServer();

  Serial.print("Camera page: http://");
  Serial.println(WiFi.localIP());

  Serial.print("Video stream: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/stream");
}

void loop() {
  delay(1000);
}