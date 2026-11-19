// The register editor supports the I²C transactions implemented by the Pi backend.
export function designSensor({dialog,api,refresh,feedback}){
 const num=(name,label,value,max=255,min=0)=>`<label>${label}<input required type="number" name="${name}" value="${value}" min="${min}" max="${max}"></label>`;
 const row=i=>`<fieldset data-output><legend>Output ${i+1}</legend><label>Signal<input name="signal" required pattern="[a-z][a-z0-9-]{0,23}" value="value-${i+1}"></label>${num('register','High-byte register',16+2*i,254)}<label>Register units<input name="unit" list="sensor-units" value="counts" maxlength="48" required></label>${num('initial','Initial value',0,1000000,-1000000)}${num('offset','Zero offset',0,1000000,-1000000)}${num('counts','Counts per scale unit',1,1000000,1)}${num('divisor','Scale unit',1,1000000,1)}<details><summary>Selectable sensitivity</summary><label>Range register (optional)<input type="number" name="range_register" min="0" max="255"></label>${num('range_shift','First bit of two-bit range',0,6)}<small>Each step doubles full scale.</small></details></fieldset>`;
 dialog('New I²C register model',`<p>Raspberry Pi 4B · Linux i2c-dev · signed 16-bit big-endian outputs in one burst (up to 32 bytes).</p><div class="model-designer"><datalist id="sensor-units">${['counts','millig','millidegrees Celsius','millidegrees per second','milli-microtesla'].map(unit=>`<option value="${unit}"></option>`).join('')}</datalist><div class="register-editor"><div class="register-identity"><label>Model ID<input name="name" value="lab_sensor" required pattern="lab_[a-z][a-z0-9_]{0,10}"></label>${num('address','I²C address (decimal)',72,119,8)}${num('id_register','Identity register',0)}${num('id_value','Identity byte',66)}</div><section id="register-outputs">${row(0)}</section><button id="add-register-output" type="button">+ Output</button><section id="control-registers"></section><button id="add-control" type="button">+ Initialization write</button></div>
 <aside class="model-preview" aria-label="Sensor model preview">
  <h3>I²C sensor</h3>
  <div class="sensor-pcb"><div class="sensor-pads"><span>VCC</span><span>GND</span><span>SDA</span><span>SCL</span></div><div class="sensor-package"><strong data-preview="name"></strong><small data-preview="address"></small></div></div>
  <h3>Register map</h3><div class="register-map"></div>
  <h3>Model definition</h3><code data-preview="definition"></code>
 </aside></div><p>After saving, install the updated emulator image in <a href="/infrastructure?target=qemu">workspace setup</a>, then add the device and test it on the workbench.</p>`,async values=>{
  const parse=node=>Object.fromEntries([...node.querySelectorAll('input,select')].map(el=>[el.name,el.type==='number'?(el.value===''?null:Number(el.value)):el.value]));
  const outputs=[...document.querySelectorAll('[data-output]')].map(node=>{const {signal,...values}=parse(node);if(values.range_register===null){delete values.range_register;delete values.range_shift;}return {name:signal,...values};});
  const controls=[...document.querySelectorAll('[data-control]')].map(parse);
  const saved=await api('hardware/model',{name:values.name,address:Number(values.address),id_register:Number(values.id_register),id_value:Number(values.id_value),outputs,controls});await refresh();feedback('Model saved to '+saved.definition+'. Install the updated emulator image before booting.');
 });
 const designer=document.querySelector('.model-designer');
 const list=designer.querySelector('#register-outputs');
 const hex=value=>Number.isInteger(value)?'0x'+value.toString(16).toUpperCase().padStart(2,'0'):'—';
 function updatePreview(){
  const input=name=>designer.querySelector('[name="'+name+'"]');
  const model=input('name').value;
  designer.querySelector('[data-preview=name]').textContent=model;
  designer.querySelector('[data-preview=definition]').textContent='project/drivers/models/'+model+'/model.json';
  designer.querySelector('[data-preview=address]').textContent='I²C · '+hex(input('address').valueAsNumber);
  const map=designer.querySelector('.register-map');
  map.replaceChildren();
  function register(address,description){
   const line=document.createElement('div'),key=document.createElement('code'),label=document.createElement('span');
   key.textContent=hex(address);label.textContent=description;line.append(key,label);map.append(line);
  }
  register(input('id_register').valueAsNumber,'Identity · '+hex(input('id_value').valueAsNumber));
  for(const row of list.children){
   const name=row.querySelector('[name=signal]').value,high=row.querySelector('[name=register]').valueAsNumber;
   register(high,name+' · high byte');register(high+1,name+' · low byte');
  }
  for(const row of designer.querySelectorAll('[data-control]')){
   register(row.querySelector('[name=register]').valueAsNumber,'Initialize · '+hex(row.querySelector('[name=setup]').valueAsNumber));
  }
 }
 designer.addEventListener('input',updatePreview);
 updatePreview();
 document.querySelector('#add-register-output').onclick=e=>{list.insertAdjacentHTML('beforeend',row(list.children.length));e.currentTarget.disabled=list.children.length>=16;updatePreview();};
 document.querySelector('#add-control').onclick=()=>{document.querySelector('#control-registers').insertAdjacentHTML('beforeend',`<fieldset data-control><legend>Control register</legend>${num('register','Address',2)}${num('reset','Reset byte',0)}${num('setup','Driver writes',1)}<details><summary>Power and reset behavior</summary>${num('sleep_mask','Sleep bits (mask)',0)}${num('reset_mask','Software reset bits (mask)',0)}</details></fieldset>`);updatePreview();};
}
