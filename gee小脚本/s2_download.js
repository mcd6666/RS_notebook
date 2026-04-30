// 1. 自动识别研究区
var roi = ee.FeatureCollection('projects/ee-machendong88/assets/mlhw');
/**
 * GEE 专家版：2025 Sentinel-2 图层叠加合成 (Visual Integrity Mosaic)
 * * 核心理念：
 * 1. 【拒绝像素破碎】：不再打散像素。采用整景叠加，最大程度保留影像的原始纹理。
 * 2. 【最优点在上】：自动将云量最少、质量最好的影像放在最顶层。
 * 3. 【水体保护】：保留了 MNDWI 水体救援机制，防止水面被误删。
 */

Map.centerObject(roi, 10);
// 只显示边框，不填充，方便看图
Map.addLayer(roi.style({color: 'red', fillColor: '00000000'}), {}, '研究区范围');

// 2. 强力去云函数 (MNDWI 水体保护版)
function maskS2clouds(image) {
  var scl = image.select('SCL');
  var mndwi = image.normalizedDifference(['B3', 'B11']);

  // 1. 严格去除实云 (8,9,10,11)
  var isCloud = scl.eq(8).or(scl.eq(9)).or(scl.eq(10)).or(scl.eq(11));
  
  // 2. 只有效水体判定 (MNDWI > -0.4)
  // 泥沙水通常 MNDWI 比较低，给一个宽松阈值
  var isLikelyWater = mndwi.gt(-0.4);

  // 3. 去云影：如果是水，则保留；如果不是水且是云影(3)，则去除
  var isShadow = scl.eq(3);
  var mask = isCloud.not().and( isShadow.not().or(isLikelyWater) );

  // 这里只去云，保留原始像素值
  return image.updateMask(mask)
              .divide(10000)
              .copyProperties(image, ["system:time_start", "CLOUDY_PIXEL_PERCENTAGE"]);
}

// 3. 循环处理
for (var i = 1; i <= 12; i++) {
  
  var month = i;
  var startDate = ee.Date.fromYMD(2025, month, 1);
  var endDate = startDate.advance(1, 'month');
  var monthString = month < 10 ? '0' + month : '' + month;
  
  // 仅测试 2 月 (如果想跑所有月份，请注释掉这一行)
  // if (month !== 2) continue; 

  // --- 4. 构建集合 ---
  var s2Col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(roi)
    .filterDate(startDate, endDate)
    .map(maskS2clouds);

  // =======================================================
  // 5. 核心算法: 智能图层叠加 (Smart Stack)
  // =======================================================
  
  // 排序：false = 降序 (云多的排前面，云少的排后面)
  // 因为 mosaic() 是“后来居上”，所以云最少的“好图”会盖在最上面。
  var finalMosaic = s2Col.sort('CLOUDY_PIXEL_PERCENTAGE', false).mosaic();
  
  // 【关键修改】：这里删除了 .clip(roi)
  // finalMosaic = finalMosaic.clip(roi); // <--- 已注释，不再裁剪

  // =======================================================

  // --- 6. 可视化 & 导出 ---
  var vis = {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3};
  
  if (month === 2) {
      Map.addLayer(finalMosaic, vis, '整景叠加_无裁剪_M02', true);
  } else {
      Map.addLayer(finalMosaic, vis, '整景叠加_无裁剪_M' + monthString, false);
  }

  var exportBands = ['B1','B2','B3','B4','B5','B6','B7','B8','B8A','B9','B11','B12'];
  
  Export.image.toDrive({
    image: finalMosaic.select(exportBands),
    description: 'S2_NoClip_2025_M' + monthString,
    folder: 'Sentinel2_2025_Month_' + monthString,
    
    // 【导出范围】：使用 .bounds() 获取外接矩形
    // 这样导出的图像就是方方正正的，不会按照 roi 的形状去切
    region: roi.geometry().bounds(),
    
    scale: 10,
    maxPixels: 1e13,
    // 强制尝试单文件
    crs: 'EPSG:4326',
    fileFormat: 'GeoTIFF'
  });
}

print('已去除裁剪步骤。导出的影像将为完整的矩形范围。');