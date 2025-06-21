[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/KeithCu/LinuxReport)

![LinuxReport logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/linuxreportfancy.webp)
**and**
![CovidReport logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/covidreportfancy.webp)
**and**
![AIReport_logo](https://linuxreportstatic.us-ord-1.linodeobjects.com/aireportfancy.webp)

--------------------------------------------------------------------------------
Simple and fast news site based on Python / Flask. Meant to be a http://drudgereport.com/ clone for Linux or Covid-19 news, updated automatically 24/7, and customizable by the user, including custom feeds and the critically important dark mode.

Here's the running code for Linux, Covid, and AI, Solar / PV, and Detroit Techno:

https://linuxreport.net 

https://covidreport.org

https://aireport.keithcu.com

https://pvreport.org

https://news.thedetroitilove.com

Takes advantage of thread pools and Apache process pools to be high-performance and scalable. Some people incorrectly say that Python is slow, but this app typically starts returning the page after less than 10 lines of my Python code.

It now auto-updates the top headlines using LLMs through [OpenRouter.ai](https://openrouter.ai), which provides access to a wide variety of AI models. To keep things interesting, the system randomly selects from over 30 free models, including [Llama 4](https://openrouter.ai/models/meta-llama/llama-4-maverick), [Qwen](https://openrouter.ai/models/qwen/qwen3-32b), and [Mistral](https://openrouter.ai/models/mistralai/mistral-small-3.1-24b-instruct) variants. If a model fails, it falls back to [Mistral Small](https://openrouter.ai/models/mistralai/mistral-small-3.1-24b-instruct) - a solid, inexpensive model that consistently delivers good headlines. See the [model selection logic](https://github.com/KeithCu/LinuxReport/blob/master/auto_update.py) in `auto_update.py`.

Feel free to request more default RSS feeds, or send pull requests.

Web servers need a configuration file to tell it where the flask software is located. A sample Apache one is included.

```bash
$ git clone https://github.com/KeithCu/LinuxReport
$ cd linuxreport
$ sudo pip install -r requirements.txt
$ python -m flask run
```

## FastAPI vs Flask for This Project

While FastAPI is a modern, high-performance framework with excellent async support, this project intentionally uses Flask for several reasons:

1. **Simplicity**: Flask's synchronous model is straightforward and matches the project's needs. The current implementation uses thread pools and Apache process pools for scaling, which works well for this use case.

2. **Maturity**: Flask has been battle-tested for years and has a vast ecosystem of extensions and community support.

3. **Performance**: The current implementation achieves good performance through thread pools and caching.

4. **Development Speed**: Flask's simplicity allows for rapid development and easier maintenance, which is crucial for a project that needs to be easily modifiable.

While FastAPI offers benefits like automatic API documentation, better type checking, and modern async support, these advantages are less relevant for this project because:
- The site primarily serves HTML pages rather than JSON APIs
- The current synchronous code is already performant enough
- The project doesn't heavily utilize type hints
- The existing thread pool implementation works well for the use case

If you're considering switching to FastAPI, you would need to:
1. Rewrite the core application logic
2. Modify the Apache configuration
3. Potentially restructure the caching system
4. Update all dependencies and extensions

The effort required for this switch might not justify the benefits for this specific use case.

## Admin Mode Security

The application has an admin mode that allows editing headlines and other admin-only functions. Admin mode is protected by a password stored in `config.yaml`.

The repository includes a default config file with a default password:

```yaml
# LinuxReport Configuration
# IMPORTANT: Change this default password for security!

# Admin settings
admin:
  password: "LinuxReportAdmin2024"
```

**IMPORTANT:** For security, you should change the default password immediately after cloning the repository by editing the `config.yaml` file.

