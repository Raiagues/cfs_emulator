import {moduleGroups, moduleChoices} from './mission-diagram.js';

export function openModuleAction(groupKey, action, workspace, {dialog, esc, prepare, change, rename}) {
  const group = moduleGroups(workspace)[groupKey];
  const choices = moduleChoices(group, action);
  const revision = workspace.mission.source.hash;
  const {kind} = group;
  const nameField = (label, value = '') => `<label>${label}<input name="newName" value="${esc(value)}" placeholder="${kind === 'library' ? 'example_lib' : 'example_app'}" required pattern="[a-z][a-z0-9]*(_[a-z0-9]+)*" maxlength="19" title="Lowercase snake_case, up to 19 characters" autocomplete="off"></label>`;
  const option = (value, label) => `<option value="${esc(value)}">${esc(label)}</option>`;
  const create = action === 'new' && group.create;
  const options = choices.map(item => option(item.name, item.name)).join('');
  const selector = create && !choices.length ? '' : `<label>${action === 'new' ? 'Module to add' : 'Module'}<select name="module" required>
    ${create ? option('@create', 'Create a new ' + kind) : ''}${options}</select></label>`;
  const title = {new: 'New', edit: 'Edit', remove: 'Remove'}[action] + ' · ' + group.title;
  const form = document.querySelector('#dialog-form');
  const body = document.querySelector('#dialog-body');
  function updateFields() {
    const name = form.elements.module?.value;
    const selected = choices.find(item => item.name === name);
    let fields = '', submit = 'Apply';
    if (action === 'remove') {
      fields = '<p>The module will leave the CPU1 build and startup. Its source files stay in the project.</p>';
      submit = 'Remove from mission';
    } else if (action === 'new') {
      if (create && (!name || name === '@create')) {
        fields = nameField('Module name');
        submit = 'Configure ' + kind;
      } else {
        submit = 'Add to mission';
      }
    } else if (selected) {
      const actions = [];
      if (selected.managed || selected.renamable) actions.push(option('rename', 'Rename module'));
      if (selected.managed) actions.push(option('configure', 'Configure startup and schedule'));
      if (kind === 'app' && !selected.required) actions.push(option(selected.enabled ? 'disable' : 'enable', selected.enabled ? 'Disable startup' : 'Enable startup'));
      fields = `<label>Change<select name="operation">${actions.join('')}</select></label><div data-rename-fields></div>`;
      if (groupKey === 'cfs') fields += '<p>NASA modules use their original flight identifiers.</p>';
      submit = 'Save change';
    }
    body.querySelector('[data-module-fields]').innerHTML = fields;
    const operation = form.elements.operation;
    if (operation) {
      const updateOperation = () => {
        body.querySelector('[data-rename-fields]').innerHTML = operation.value === 'rename'
          ? nameField('New module name', name) + '<p>Renaming updates the source files, native symbols and mission references.</p>' : '';
        form.querySelector('[type="submit"]').textContent = operation.value === 'configure' ? 'Configure app' : submit;
      };
      operation.onchange = updateOperation;
      updateOperation();
    } else {
      form.querySelector('[type="submit"]').textContent = submit;
    }
    document.querySelector('#dialog-error').textContent = '';
  }
  dialog(title, selector + '<div data-module-fields></div>', async values => {
    if (action === 'remove') return change('remove', values.module, kind, revision);
    if (action === 'new') {
      if (create && (!values.module || values.module === '@create')) return prepare(kind, values.newName, 'create', revision);
      return change('add', values.module, kind, revision);
    }
    if (values.operation === 'rename') return rename(kind, values.module, values.newName, revision);
    if (values.operation === 'configure') return prepare(kind, values.module, 'edit', revision);
    return change(values.operation, values.module, kind, revision);
  });
  if (form.elements.module) form.elements.module.onchange = updateFields;
  updateFields();
  (form.elements.module || form.elements.newName)?.focus();
}
