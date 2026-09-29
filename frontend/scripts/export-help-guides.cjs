// Export the same React guide sections that the /help page renders.
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === "./HelpPage" && parent?.filename.includes(`${path.sep}pages${path.sep}help${path.sep}`)) {
    return {
      Shot: ({ src, caption }) => React.createElement("figure", null,
        React.createElement("img", { src, alt: caption }),
        React.createElement("figcaption", null, caption)),
      Note: ({ children, warn }) => React.createElement("aside", { "data-warn": Boolean(warn) }, children),
    };
  }
  return originalLoad(request, parent, isMain);
};

require.extensions[".tsx"] = function (module, filename) {
  const output = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
    fileName: filename,
  }).outputText;
  module._compile(output, filename);
};

const base = path.join(__dirname, "..", "src", "pages", "help");
const guides = [
  ["А", "Руководство менеджера", "ManagerGuide"],
  ["Б", "Руководство руководителя", "HeadGuide"],
  ["В", "Руководство администратора", "AdminGuide"],
  ["Г", "Руководство по установке и эксплуатации", "OperationsGuide"],
];
const result = guides.map(([letter, title, name]) => ({
  letter,
  title,
  sections: require(path.join(base, `${name}.tsx`))[name]().map(({ id, title, body }) => ({
    id,
    title,
    html: renderToStaticMarkup(body),
  })),
}));
process.stdout.write(JSON.stringify(result));
