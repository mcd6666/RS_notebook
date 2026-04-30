/**
 * 将静态 Asset 影像下载到 Google Drive
 */

// 1. 引用你已经生成的静态 Asset 图像
// 请确保路径与你 Assets 选项卡中的完整路径一致
var finalAsset = ee.Image('projects/ee-machendong88/assets/TidalFlat_Result_18_25_Final');

// 2. 执行导出到 Drive 的任务
Export.image.toDrive({
  image: finalAsset,
  description: 'TidalFlat_Final_Download', // 任务名称
  folder: 'GEE_TidalFlat_Results',         // 网盘中的文件夹
  region: finalAsset.geometry(),           // 自动读取影像的边界
  scale: 10,                               // 保持 10 米分辨率
  crs: 'EPSG:4326',                        // 使用标准的 WGS84 坐标系
  maxPixels: 1e13
});