"""Selenium + Java (JUnit 5, Maven) project renderer."""

from __future__ import annotations

from urllib.parse import urlparse

from ats.generation.adapters.common import (
    ENV_EXAMPLE,
    ENV_PLACEHOLDER,
    GITIGNORE,
    FrameworkAdapter,
    RenderContext,
    attr_of,
    camel,
    case_function_name,
    comment_safe,
    java_str,
    locators_json,
    module_slug,
    pascal,
    py_ident,
    readme,
    step_text,
)
from ats.models import AutomationStep

JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const", "continue", "default", "do", "double",
    "else", "enum", "extends", "final", "finally", "float", "for", "goto", "if", "implements", "import", "instanceof", "int", "interface",
    "long", "native", "new", "package", "private", "protected", "public", "return", "short", "static", "strictfp", "super", "switch",
    "synchronized", "this", "throw", "throws", "transient", "try", "void", "volatile", "while", "true", "false", "null", "var", "record",
}  # fmt: skip


def java_name(text: str) -> str:
    value = camel(text)
    return value + "_" if value in JAVA_KEYWORDS else value


POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>studio.generated</groupId>
  <artifactId>ai-generated-tests</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.seleniumhq.selenium</groupId>
      <artifactId>selenium-java</artifactId>
      <version>4.27.0</version>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.3</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>com.google.code.gson</groupId>
      <artifactId>gson</artifactId>
      <version>2.11.0</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
        <configuration>
          <reportsDirectory>${project.basedir}/reports/junit</reportsDirectory>
          <trimStackTrace>false</trimStackTrace>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
"""

JAVA_APP = r"""package studio.support;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.openqa.selenium.By;
import org.openqa.selenium.OutputType;
import org.openqa.selenium.TakesScreenshot;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.logging.LogEntry;
import org.openqa.selenium.support.ui.WebDriverWait;
import studio.pages.Pages;

public class App {
    @FunctionalInterface
    public interface Body {
        void run() throws Exception;
    }

    private static final Pattern ENV = Pattern.compile("\\{\\{env:([A-Za-z_][A-Za-z0-9_]*)\\}\\}");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();

    public final WebDriver driver;
    public final Pages pages;
    public final long timeoutSeconds;
    private final String baseUrl;
    private final String testCaseId;
    private final JsonObject locators;
    private final List<Map<String, Object>> steps = new ArrayList<>();
    private Map<String, Object> failure = new LinkedHashMap<>();

    public App(WebDriver driver, String baseUrl, String testCaseId) throws Exception {
        this.driver = driver;
        this.baseUrl = baseUrl.replaceAll("/+$", "") + "/";
        this.testCaseId = testCaseId;
        String timeout = System.getenv("STEP_TIMEOUT");
        this.timeoutSeconds = timeout == null || timeout.isBlank() ? 10 : Long.parseLong(timeout.trim());
        Path file = Paths.get(System.getProperty("user.dir"), "config", "locators.json");
        this.locators = JsonParser.parseString(Files.readString(file, StandardCharsets.UTF_8)).getAsJsonObject();
        this.pages = new Pages(this);
    }

    /** Substitute {{env:NAME}} placeholders from the environment (values never appear in code or reports). */
    public String val(String text) {
        Matcher matcher = ENV.matcher(text);
        StringBuilder out = new StringBuilder();
        while (matcher.find()) {
            String value = System.getenv(matcher.group(1));
            if (value == null) {
                throw new AssertionError("Environment variable " + matcher.group(1) + " is not set");
            }
            matcher.appendReplacement(out, Matcher.quoteReplacement(value));
        }
        matcher.appendTail(out);
        return out.toString();
    }

    public By by(String key) {
        if (!locators.has(key)) {
            throw new AssertionError("Unknown element key: " + key);
        }
        JsonObject resolved = locators.getAsJsonObject(key).getAsJsonObject("resolved");
        String value = resolved.get("value").getAsString();
        return "xpath".equals(resolved.get("by").getAsString()) ? By.xpath(value) : By.cssSelector(value);
    }

    public WebDriverWait waiter() {
        return new WebDriverWait(driver, Duration.ofSeconds(timeoutSeconds));
    }

    public void open(String target) {
        String url = target.matches("^https?://.*") ? target : baseUrl + target.replaceAll("^/+", "");
        driver.get(url);
    }

    public void expectUrlContains(String text) {
        waiter().withMessage("URL does not contain '" + text + "'").until(d -> d.getCurrentUrl().contains(text));
    }

    public void expectTitleContains(String text) {
        waiter().withMessage("Title does not contain '" + text + "'").until(d -> d.getTitle().contains(text));
    }

    public void step(String description, String action, String element, Body body) throws Exception {
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("index", steps.size() + 1);
        record.put("description", description);
        record.put("action", action);
        record.put("element", element);
        record.put("status", "running");
        steps.add(record);
        try {
            body.run();
            record.put("status", "passed");
        } catch (Throwable error) {
            String message = String.valueOf(error.getMessage());
            record.put("status", "failed");
            record.put("error", message.substring(0, Math.min(message.length(), 1500)));
            failure = new LinkedHashMap<>();
            failure.put("step", record.get("index"));
            failure.put("action", action);
            failure.put("element", element);
            failure.put("error", record.get("error"));
            throw error;
        }
    }

    public void finish(boolean failed) throws Exception {
        Path folder = Paths.get(System.getProperty("user.dir"), "reports", "evidence", testCaseId);
        Files.createDirectories(folder);
        Files.writeString(folder.resolve("steps.json"), GSON.toJson(steps), StandardCharsets.UTF_8);
        if (!failed) {
            return;
        }
        Map<String, Object> info = new LinkedHashMap<>();
        info.put("test_case_id", testCaseId);
        info.putAll(failure);
        try {
            info.put("url", driver.getCurrentUrl());
            info.put("title", driver.getTitle());
            String source = driver.getPageSource();
            Files.writeString(folder.resolve("dom.html"), source.substring(0, Math.min(source.length(), 500000)), StandardCharsets.UTF_8);
            byte[] png = ((TakesScreenshot) driver).getScreenshotAs(OutputType.BYTES);
            Files.write(folder.resolve("screenshot.png"), png);
            List<String> console = new ArrayList<>();
            try {
                for (LogEntry entry : driver.manage().logs().get("browser")) {
                    String text = entry.getLevel() + ": " + entry.getMessage();
                    console.add(text.substring(0, Math.min(text.length(), 300)));
                }
            } catch (Exception ignored) {
                // console logs are not available for every browser
            }
            info.put("console", console.subList(Math.max(0, console.size() - 20), console.size()));
        } catch (Exception error) {
            info.put("evidence_error", String.valueOf(error.getMessage()));
        }
        Files.writeString(folder.resolve("failure.json"), GSON.toJson(info), StandardCharsets.UTF_8);
    }
}
"""

JAVA_ELEMENT = r"""package studio.support;

import org.openqa.selenium.Keys;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.interactions.Actions;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.Select;

/** Element wrapper with explicit waits. Mirrors the Playwright page-object API so tests read the same. */
public class Element {
    private final App app;
    private final String key;

    public Element(App app, String key) {
        this.app = app;
        this.key = key;
    }

    private static CharSequence toKey(String name) {
        if (name.length() == 1) {
            return name;
        }
        String constant = name.replaceAll("([a-z0-9])([A-Z])", "$1_$2").toUpperCase();
        try {
            return Keys.valueOf(constant);
        } catch (IllegalArgumentException error) {
            return name;
        }
    }

    public WebElement find() {
        return app.waiter().withMessage("Element not found: " + key).until(ExpectedConditions.presenceOfElementLocated(app.by(key)));
    }

    private WebElement interactable() {
        return app.waiter().withMessage("Element not clickable: " + key).until(ExpectedConditions.elementToBeClickable(app.by(key)));
    }

    public void click() {
        interactable().click();
    }

    public void dblclick() {
        new Actions(app.driver).doubleClick(interactable()).perform();
    }

    public void fill(String text) {
        WebElement element = interactable();
        element.clear();
        element.sendKeys(text);
    }

    public void clear() {
        interactable().clear();
    }

    public void selectOption(String label) {
        new Select(interactable()).selectByVisibleText(label);
    }

    public void check() {
        WebElement element = interactable();
        if (!element.isSelected()) {
            element.click();
        }
    }

    public void uncheck() {
        WebElement element = interactable();
        if (element.isSelected()) {
            element.click();
        }
    }

    public void press(String keyName) {
        find().sendKeys(toKey(keyName));
    }

    public void hover() {
        new Actions(app.driver).moveToElement(find()).perform();
    }

    public void expectVisible() {
        app.waiter().withMessage("Element not visible: " + key).until(ExpectedConditions.visibilityOfElementLocated(app.by(key)));
    }

    public void expectHidden() {
        app.waiter().withMessage("Element still visible: " + key).until(ExpectedConditions.invisibilityOfElementLocated(app.by(key)));
    }

    public void expectText(String text) {
        app.waiter().withMessage("Text '" + text + "' not found in " + key).until(d -> find().getText().contains(text));
    }

    public void expectValue(String text) {
        app.waiter().withMessage("Value of " + key + " is not '" + text + "'").until(d -> text.equals(find().getAttribute("value")));
    }

    public void expectEnabled() {
        app.waiter().withMessage(key + " is not enabled").until(d -> find().isEnabled());
    }

    public void expectDisabled() {
        app.waiter().withMessage(key + " is not disabled").until(d -> !find().isEnabled());
    }
}
"""

JAVA_BASE_TEST = r"""package studio.support;

import java.io.File;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInfo;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.junit.jupiter.api.extension.TestExecutionExceptionHandler;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.edge.EdgeDriver;
import org.openqa.selenium.edge.EdgeOptions;
import org.openqa.selenium.firefox.FirefoxDriver;
import org.openqa.selenium.firefox.FirefoxOptions;
import org.openqa.selenium.logging.LogType;
import org.openqa.selenium.logging.LoggingPreferences;
import java.util.logging.Level;

public abstract class BaseTest {
    protected static final String DEFAULT_BASE_URL = Config.DEFAULT_BASE_URL;
    protected static final String DEFAULT_BROWSER = Config.DEFAULT_BROWSER;

    protected App app;
    private WebDriver driver;
    private boolean failed;

    @RegisterExtension
    protected final TestExecutionExceptionHandler recorder = (context, throwable) -> {
        failed = true;
        throw throwable;
    };

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static WebDriver buildDriver(String browser) {
        boolean headless = !"0".equals(System.getenv("HEADLESS"));
        boolean insecure = "1".equals(System.getenv("IGNORE_HTTPS_ERRORS"));
        if (System.getenv("CHROMEDRIVER") != null) {
            System.setProperty("webdriver.chrome.driver", System.getenv("CHROMEDRIVER"));
        }
        if ("firefox".equals(browser)) {
            FirefoxOptions options = new FirefoxOptions();
            if (headless) {
                options.addArguments("-headless");
            }
            options.setAcceptInsecureCerts(insecure);
            return new FirefoxDriver(options);
        }
        LoggingPreferences logs = new LoggingPreferences();
        logs.enable(LogType.BROWSER, Level.ALL);
        if ("edge".equals(browser)) {
            EdgeOptions options = new EdgeOptions();
            options.addArguments("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900");
            if (headless) {
                options.addArguments("--headless=new");
            }
            options.setAcceptInsecureCerts(insecure);
            options.setCapability("goog:loggingPrefs", logs);
            return new EdgeDriver(options);
        }
        ChromeOptions options = new ChromeOptions();
        options.addArguments("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1366,900");
        if (headless) {
            options.addArguments("--headless=new");
        }
        String binary = System.getenv("CHROME_BIN");
        if (binary != null && !binary.isBlank() && new File(binary).exists()) {
            options.setBinary(binary);
        }
        options.setAcceptInsecureCerts(insecure);
        options.setCapability("goog:loggingPrefs", logs);
        return new ChromeDriver(options);
    }

    @BeforeEach
    protected void startSession(TestInfo info) throws Exception {
        String testCaseId = info.getTags().stream().filter(t -> t.matches("(?i)TC_[A-Z0-9]+_\\d{3}")).findFirst().orElse("UNKNOWN");
        driver = buildDriver(env("BROWSER", DEFAULT_BROWSER).toLowerCase());
        app = new App(driver, env("BASE_URL", DEFAULT_BASE_URL), testCaseId);
    }

    @AfterEach
    protected void endSession() throws Exception {
        try {
            if (app != null) {
                app.finish(failed);
            }
        } finally {
            if (driver != null) {
                driver.quit();
            }
        }
    }
}
"""

JAVA_BASE_PAGE = r"""package studio.pages;

import studio.support.App;
import studio.support.Element;

public abstract class BasePage {
    protected final App app;

    protected BasePage(App app) {
        this.app = app;
    }

    public abstract String path();

    protected Element element(String key) {
        return new Element(app, key);
    }

    public void open() {
        app.open(path());
    }
}
"""


class SeleniumJavaAdapter(FrameworkAdapter):
    key = "selenium_java"

    def render(self, ctx: RenderContext) -> dict[str, str]:
        used: dict[str, list[str]] = {}
        for item in ctx.cases:
            for step in item.script.steps:
                if step.element:
                    bucket = used.setdefault(ctx.locators[step.element].page_key, [])
                    if step.element not in bucket:
                        bucket.append(step.element)

        def ref(key: str) -> str:
            return f"app.pages.{java_name(py_ident(ctx.locators[key].page_key, 'page'))}.{java_name(attr_of(key))}()"

        base = "src/test/java/studio"
        files: dict[str, str] = {"pom.xml": POM}
        class_names: set[str] = set()
        for module_key, items in ctx.modules().items():
            name = pascal(module_slug(module_key))
            while name + "Test" in class_names:
                name += "X"
            class_names.add(name + "Test")
            files[f"{base}/tests/{name}Test.java"] = self._tests(module_key, name + "Test", items, ref)
        for page_key, keys in used.items():
            files[f"{base}/pages/{pascal(page_key)}Page.java"] = self._page(ctx, page_key, keys)
        files[f"{base}/pages/Pages.java"] = self._pages(used)
        files[f"{base}/pages/BasePage.java"] = JAVA_BASE_PAGE
        files[f"{base}/support/App.java"] = JAVA_APP
        files[f"{base}/support/Element.java"] = JAVA_ELEMENT
        files[f"{base}/support/BaseTest.java"] = JAVA_BASE_TEST
        files[f"{base}/support/Config.java"] = (
            "package studio.support;\n\nfinal class Config {\n"
            f"    static final String DEFAULT_BASE_URL = {java_str(ctx.base_url)};\n"
            f"    static final String DEFAULT_BROWSER = {java_str(ctx.browser)};\n\n    private Config() {{\n    }}\n}}\n"
        )
        files["config/locators.json"] = locators_json(ctx, selenium=True)
        files["README.md"] = readme(ctx, "Selenium + Java", "mvn -q -DskipTests compile", f"BROWSER={ctx.browser} mvn test")
        files[".gitignore"] = GITIGNORE
        files[".env.example"] = ENV_EXAMPLE
        return files

    # ------------------------------------------------------------------
    def _tests(self, module: str, class_name: str, items: list, ref) -> str:  # type: ignore[no-untyped-def]
        lines = [
            "package studio.tests;", "", "import org.junit.jupiter.api.DisplayName;", "import org.junit.jupiter.api.Tag;", "import org.junit.jupiter.api.Test;",
            "import studio.support.BaseTest;", "", f"/** Automated tests for module: {comment_safe(module)} (generated by AI Autonomous Testing Studio). */",
            f"class {class_name} extends BaseTest {{",
        ]  # fmt: skip
        used_names: set[str] = set()
        for item in items:
            tc, script = item.test_case, item.script
            method = case_function_name(tc.test_case_id, tc.title).removeprefix("test_")
            while method in used_names:
                method += "_x"
            used_names.add(method)
            lines += [
                "", "    @Test", f"    @Tag({java_str(tc.test_case_id)})", f"    @DisplayName({java_str(tc.test_case_id + ' - ' + tc.title)})",
                f"    // Scenario {tc.scenario_id} | Expected: {comment_safe(tc.expected_result, 200)}",
            ]  # fmt: skip
            if script.notes:
                lines.append(f"    // Note: {comment_safe(script.notes, 200)}")
            lines.append(f"    void {method}() throws Exception {{")
            for step in script.steps:
                lines.append(f"        app.step({java_str(step_text(step, tc))}, {java_str(step.action)}, {java_str(step.element or '')}, () -> {self._statement(step, ref)});")
            if not script.steps:
                lines.append('        org.junit.jupiter.api.Assumptions.assumeTrue(false, "No automatable steps");')
            lines.append("    }")
        lines.append("}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _statement(step: AutomationStep, ref) -> str:  # type: ignore[no-untyped-def]
        loc = ref(step.element) if step.element else ""
        text = step.value or ""
        v = f"app.val({java_str(text)})" if ENV_PLACEHOLDER.search(text) else java_str(text)
        mapping = {
            "goto": f"app.open({v})",
            "click": f"{loc}.click()",
            "dblclick": f"{loc}.dblclick()",
            "fill": f"{loc}.fill({v})",
            "clear": f"{loc}.clear()",
            "select": f"{loc}.selectOption({v})",
            "check": f"{loc}.check()",
            "uncheck": f"{loc}.uncheck()",
            "press": f"{loc}.press({v})",
            "hover": f"{loc}.hover()",
            "expect_visible": f"{loc}.expectVisible()",
            "expect_hidden": f"{loc}.expectHidden()",
            "expect_text": f"{loc}.expectText({v})",
            "expect_value": f"{loc}.expectValue({v})",
            "expect_enabled": f"{loc}.expectEnabled()",
            "expect_disabled": f"{loc}.expectDisabled()",
            "expect_url_contains": f"app.expectUrlContains({v})",
            "expect_title_contains": f"app.expectTitleContains({v})",
        }
        return mapping[step.action]

    @staticmethod
    def _page(ctx: RenderContext, page_key: str, keys: list[str]) -> str:
        url = next((ctx.locators[k].page_url for k in keys if ctx.locators[k].page_url), "/")
        parsed = urlparse(url)
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        cls = f"{pascal(page_key)}Page"
        lines = [
            "package studio.pages;", "", "import studio.support.App;", "import studio.support.Element;", "",
            f"/** Page object for {comment_safe(path)} */", f"public class {cls} extends BasePage {{", f"    public {cls}(App app) {{", "        super(app);", "    }", "",
            "    @Override", "    public String path() {", f"        return {java_str(path)};", "    }",
        ]  # fmt: skip
        for key in keys:
            spec = ctx.locators[key]
            lines += [
                "", f"    /** {comment_safe(spec.intent or spec.name or spec.role or key, 80)} */",
                f"    public Element {java_name(attr_of(key))}() {{", f"        return element({java_str(key)});", "    }",
            ]  # fmt: skip
        lines.append("}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _pages(used: dict[str, list[str]]) -> str:
        lines = ["package studio.pages;", "", "import studio.support.App;", "", "public class Pages {"]
        lines += [f"    public final {pascal(k)}Page {java_name(py_ident(k, 'page'))};" for k in used]
        lines += ["", "    public Pages(App app) {"]
        lines += [f"        this.{java_name(py_ident(k, 'page'))} = new {pascal(k)}Page(app);" for k in used]
        lines += ["    }", "}"]
        return "\n".join(lines) + "\n"
